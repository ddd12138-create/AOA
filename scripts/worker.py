"""Worker process: sdr -> detect/aoa hooks -> ZMQ PUB/REP.

detect/aoa are empty callbacks (no MUSIC). Replay does not import UHD.
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any

import yaml
import zmq

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sdr.channel_map import ChannelMap, assert_live_allowed, load_channel_map
from sdr.cli import add_source_args
from sdr.errors import LiveRejected, ReplayError, SdrError
from sdr.iqframe import IqFrame
from sdr.replay import ReplaySource

DEFAULT_PUB = "tcp://127.0.0.1:5556"
DEFAULT_REP = "tcp://127.0.0.1:5557"
DEFAULT_ARRAY = "configs/array_uca_m4.yaml"
STATUS_PERIOD_S = 1.0

log = logging.getLogger("worker")


def _empty_detect(_frame: IqFrame) -> None:
    """Passthrough until detect/ is implemented. Do not invent DetectionEvent here."""
    return None


def _empty_aoa(_frame: IqFrame, _event: Any = None) -> None:
    """Empty callback. MUSIC lives in aoa/, not in this worker."""
    return None


def resolve_repo_path(path: str | Path) -> Path:
    p = Path(path)
    if p.exists():
        return p
    alt = REPO_ROOT / path
    if alt.exists():
        return alt
    return p


def load_uncalibrated(array_path: Path | None) -> bool:
    if array_path is None or not array_path.is_file():
        return True
    raw = yaml.safe_load(array_path.read_text(encoding="utf-8")) or {}
    calib_rel = raw.get("calib_path")
    if not calib_rel:
        return True
    calib_path = resolve_repo_path(str(calib_rel))
    if not calib_path.is_file():
        return True
    calib = yaml.safe_load(calib_path.read_text(encoding="utf-8")) or {}
    return calib.get("status") != "calibrated"


class Worker:
    def __init__(
        self,
        source,
        *,
        pub_addr: str,
        rep_addr: str,
        replay: bool,
        M: int,
        uncalibrated: bool,
        detect=_empty_detect,
        aoa=_empty_aoa,
    ) -> None:
        self.source = source
        self.pub_addr = pub_addr
        self.rep_addr = rep_addr
        self.replay = replay
        self.M = M
        self.uncalibrated = uncalibrated
        self._detect = detect
        self._aoa = aoa
        self._lock = threading.Lock()
        self._pub_lock = threading.Lock()
        self.running = False
        self.shutdown = False
        self.state = "idle"
        self.detail = ""
        self._ctx = zmq.Context.instance()
        self._pub = self._ctx.socket(zmq.PUB)
        self._pub.setsockopt(zmq.LINGER, 0)
        self._pub.setsockopt(zmq.SNDHWM, 16)
        self._pub.bind(pub_addr)
        self._rep = self._ctx.socket(zmq.REP)
        self._rep.setsockopt(zmq.LINGER, 0)
        self._rep.bind(rep_addr)
        self._cmd_thread = threading.Thread(target=self._cmd_loop, name="worker-rep", daemon=True)

    def start_cmd_thread(self) -> None:
        self._cmd_thread.start()

    def close(self) -> None:
        self.shutdown = True
        with self._lock:
            self.running = False
            self.state = "idle"
            try:
                self.source.close()
            except Exception:
                pass
        if self._cmd_thread.is_alive():
            self._cmd_thread.join(timeout=0.6)
        self._pub.close(0)
        self._rep.close(0)

    def handle_cmd(self, msg: dict[str, Any]) -> dict[str, Any]:
        cmd = msg.get("cmd")
        try:
            if cmd == "tune":
                with self._lock:
                    self.source.tune(
                        fc_hz=msg.get("fc_hz"),
                        fs_hz=msg.get("fs_hz"),
                        gain_db=msg.get("gain_db"),
                    )
                self._publish_status()
                return {"ok": True, "error": None}
            if cmd == "start":
                self._set_running(True)
                return {"ok": True, "error": None}
            if cmd == "stop":
                self._set_running(False)
                return {"ok": True, "error": None}
            return {"ok": False, "error": f"unknown cmd: {cmd!r}"}
        except Exception as exc:
            self.state = "error"
            self.detail = str(exc)
            self._publish_status()
            return {"ok": False, "error": str(exc)}

    def _set_running(self, want: bool) -> None:
        with self._lock:
            if want:
                self.source.start()
                self.running = True
                self.state = "running"
                self.detail = ""
            else:
                self.running = False
                self.state = "idle"
                self.source.stop()
        self._publish_status()

    def status_payload(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "timestamp_utc_ns": time.time_ns(),
            "state": self.state,
            "replay": bool(self.replay),
            "M": int(self.M),
            "fc_hz": float(self.source.fc_hz),
            "uncalibrated": bool(self.uncalibrated),
            "detail": self.detail,
        }

    def _publish_status(self) -> None:
        body = json.dumps(self.status_payload(), ensure_ascii=False).encode("utf-8")
        with self._pub_lock:
            try:
                self._pub.send_multipart([b"status", body], flags=zmq.NOBLOCK)
            except zmq.Again:
                pass

    def _publish_iq(self, frame: IqFrame) -> None:
        with self._pub_lock:
            self._pub.send_multipart([b"iq", *frame.zmq_parts()])

    def _cmd_loop(self) -> None:
        poller = zmq.Poller()
        poller.register(self._rep, zmq.POLLIN)
        while not self.shutdown:
            events = dict(poller.poll(100))
            if self._rep not in events:
                continue
            raw = self._rep.recv()
            try:
                msg = json.loads(raw)
                if not isinstance(msg, dict):
                    raise ValueError("command must be a JSON object")
                resp = self.handle_cmd(msg)
            except Exception as exc:
                resp = {"ok": False, "error": str(exc)}
            self._rep.send_string(json.dumps(resp, ensure_ascii=False))

    def run(self, *, auto_start: bool) -> None:
        self.start_cmd_thread()
        time.sleep(0.2)
        self._publish_status()
        if auto_start:
            self._set_running(True)
        last_status = time.monotonic()
        while not self.shutdown:
            if self.running:
                try:
                    frame = self.source.next_frame()
                    if not self.running:
                        continue
                    self._publish_iq(frame)
                    event = self._detect(frame)
                    self._aoa(frame, event)
                except Exception as exc:
                    self.state = "error"
                    self.detail = str(exc)
                    self.running = False
                    log.exception("stream error")
                    self._publish_status()
                    if not self.replay:
                        break
                    time.sleep(0.2)
            else:
                time.sleep(0.05)
            now = time.monotonic()
            if now - last_status >= STATUS_PERIOD_S:
                self._publish_status()
                last_status = now


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="worker",
        description="sdr worker: PUB iq/status on 5556, REP tune/start/stop on 5557.",
    )
    add_source_args(parser)
    parser.add_argument("--array", default=DEFAULT_ARRAY, help="ArrayGeometry yaml")
    parser.add_argument("--pub", default=DEFAULT_PUB, help=f"PUB bind (default {DEFAULT_PUB})")
    parser.add_argument("--rep", default=DEFAULT_REP, help=f"REP bind (default {DEFAULT_REP})")
    return parser


def open_source(args: argparse.Namespace):
    if bool(args.replay) == bool(args.live):
        raise SystemExit("error: specify exactly one of --replay STEM or --live")
    if args.replay:
        return ReplaySource(resolve_repo_path(args.replay)), True, None
    cmap = load_channel_map(resolve_repo_path(args.config))
    assert_live_allowed(cmap)
    from sdr.live import LiveSource

    src = LiveSource(
        cmap,
        fc_hz=args.fc_hz,
        fs_hz=args.fs_hz,
        gain_db=args.gain_db,
        n_samp=args.n_samp,
    )
    return src, False, cmap


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = build_parser().parse_args(argv)
    try:
        source, replay, cmap = open_source(args)
    except LiveRejected as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (ReplayError, SdrError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    array_path = resolve_repo_path(args.array)
    uncalibrated = load_uncalibrated(array_path if array_path.is_file() else None)
    M = source.frame.n_chan if replay else (cmap.M if isinstance(cmap, ChannelMap) else 4)

    worker = Worker(
        source,
        pub_addr=args.pub,
        rep_addr=args.rep,
        replay=replay,
        M=M,
        uncalibrated=uncalibrated,
    )

    def _stop(*_args: object) -> None:
        worker.shutdown = True

    signal.signal(signal.SIGINT, _stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _stop)

    log.info("PUB %s  REP %s  replay=%s  M=%s", args.pub, args.rep, replay, M)
    try:
        worker.run(auto_start=replay)
    finally:
        worker.close()
    return 0 if worker.state != "error" else 1


if __name__ == "__main__":
    raise SystemExit(main())
