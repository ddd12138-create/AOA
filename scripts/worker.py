"""Worker process: sdr -> detect -> aoa.MusicEstimator -> ZMQ PUB/REP.

MUSIC runs here, never in the host process. Replay does not import UHD.
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

import zmq

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aoa.errors import MissingArrayRadiusError
from aoa.estimator import MusicEstimator
from aoa.geometry import require_radius_m
from aoa.types import IqFrame as AoAIqFrame
from detect import DetectionEvent, detect_frame
from sdr.channel_map import ChannelMap, assert_live_allowed, load_channel_map
from sdr.cli import DEFAULT_N_SAMP, add_source_args
from sdr.errors import LiveRejected, ReplayError, RxOverflow, SdrError
from sdr.iqframe import IqFrame
from sdr.replay import ReplaySource, save_replay

DEFAULT_PUB = "tcp://127.0.0.1:5556"
DEFAULT_REP = "tcp://127.0.0.1:5557"
DEFAULT_ARRAY_SIM = "configs/array_uca_m4_sim.yaml"
DEFAULT_ARRAY_HW = "configs/array_uca_m4.yaml"
STATUS_PERIOD_S = 1.0
# Default 4096 samp @ 1 Msps is 4 ms — too short for detect/MUSIC; UHD overflows.
LIVE_N_SAMP = 32_768

log = logging.getLogger("worker")


def resolve_repo_path(path: str | Path) -> Path:
    p = Path(path)
    if p.exists():
        return p
    alt = REPO_ROOT / path
    if alt.exists():
        return alt
    return p


def as_aoa_frame(frame: IqFrame) -> AoAIqFrame:
    """Map sdr.IqFrame onto aoa.IqFrame without copying IQ unless needed."""
    return AoAIqFrame(
        schema_version=int(frame.schema_version),
        frame_id=int(frame.frame_id),
        timestamp_utc_ns=int(frame.timestamp_utc_ns),
        fc_hz=float(frame.fc_hz),
        fs_hz=float(frame.fs_hz),
        n_chan=int(frame.n_chan),
        n_samp=int(frame.n_samp),
        dtype=str(frame.dtype),
        layout=str(frame.layout),
        endianness=str(frame.endianness),
        channel_ids=[int(x) for x in frame.channel_ids],
        element_ids=[int(x) for x in frame.element_ids],
        iq=frame.iq,
    )


def detection_payload(event: DetectionEvent) -> dict[str, Any]:
    return {
        "schema_version": int(event.schema_version),
        "event_id": int(event.event_id),
        "timestamp_utc_ns": int(event.timestamp_utc_ns),
        "fc_hz": float(event.fc_hz),
        "bw_hz": float(event.bw_hz),
        "snr_db": float(event.snr_db),
        "burst_start_samp": int(event.burst_start_samp),
        "burst_end_samp": int(event.burst_end_samp),
        "burst_start_utc_ns": int(event.burst_start_utc_ns),
        "burst_end_utc_ns": int(event.burst_end_utc_ns),
        "iq_ref": event.iq_ref.to_dict(),
        "band": str(event.band),
    }


class Worker:
    def __init__(
        self,
        source,
        *,
        pub_addr: str,
        rep_addr: str,
        replay: bool,
        M: int,
        estimator: MusicEstimator,
        save_stem: str | Path | None = None,
    ) -> None:
        self.source = source
        self.pub_addr = pub_addr
        self.rep_addr = rep_addr
        self.replay = replay
        self.M = M
        self._estimator = estimator
        self._save_stem = Path(save_stem) if save_stem else None
        self.uncalibrated = bool(estimator.uncalibrated)
        self._event_id = 0
        self._aoa_blocked = False
        self._lock = threading.Lock()
        self._pub_lock = threading.Lock()
        self._latest_lock = threading.Lock()
        self._latest_frame: IqFrame | None = None
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
        self._apply_radius_gate()

    def _apply_radius_gate(self) -> None:
        try:
            require_radius_m(self._estimator.geometry)
        except MissingArrayRadiusError as exc:
            # Missing R_m is not a stream failure: still publish iq/detect.
            self._aoa_blocked = True
            self.detail = str(exc)

    def start_cmd_thread(self) -> None:
        self._cmd_thread.start()

    def close(self) -> None:
        self.shutdown = True
        with self._lock:
            self.running = False
            if self.state != "error":
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
                if not self._aoa_blocked:
                    self.detail = ""
            else:
                self.running = False
                self.source.stop()
                self.state = "idle"
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

    def _publish_json(self, topic: bytes, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        with self._pub_lock:
            try:
                self._pub.send_multipart([topic, body], flags=zmq.NOBLOCK)
            except zmq.Again:
                pass

    def _publish_status(self) -> None:
        self._publish_json(b"status", self.status_payload())

    def _publish_iq(self, frame: IqFrame) -> None:
        with self._pub_lock:
            try:
                self._pub.send_multipart([b"iq", *frame.zmq_parts()], flags=zmq.NOBLOCK)
            except zmq.Again:
                pass

    def _detect_and_aoa(self, frame: IqFrame) -> None:
        events = detect_frame(frame, first_event_id=self._event_id + 1)
        if not events:
            return
        self._event_id = int(events[-1].event_id)
        aoa_frame = as_aoa_frame(frame)
        for event in events:
            self._publish_json(b"detect", detection_payload(event))
            if self._aoa_blocked:
                continue
            try:
                out = self._estimator.estimate(aoa_frame, event)
            except MissingArrayRadiusError as exc:
                self._aoa_blocked = True
                self.detail = str(exc)
                log.warning("%s", exc)
                self._publish_status()
                return
            except Exception as exc:
                log.warning("aoa estimate failed: %s", exc)
                continue
            self.uncalibrated = bool(out.uncalibrated)
            self._publish_json(b"aoa", out.aoa_json())

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

    def _live_aoa_loop(self) -> None:
        """Detect/MUSIC off the UHD recv path so a slow estimate cannot overflow RX."""
        while not self.shutdown:
            with self._latest_lock:
                frame = self._latest_frame
                self._latest_frame = None
            if frame is None:
                time.sleep(0.005)
                continue
            try:
                self._detect_and_aoa(frame)
            except Exception:
                log.exception("detect/aoa error")

    def run(self, *, auto_start: bool) -> None:
        self.start_cmd_thread()
        aoa_thread: threading.Thread | None = None
        if not self.replay:
            aoa_thread = threading.Thread(
                target=self._live_aoa_loop, name="worker-aoa", daemon=True
            )
            aoa_thread.start()
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
                    if self._save_stem is not None:
                        save_replay(self._save_stem, frame)
                    self._publish_iq(frame)
                    if self.replay:
                        self._detect_and_aoa(frame)
                    else:
                        with self._latest_lock:
                            self._latest_frame = frame
                except RxOverflow as exc:
                    log.warning("%s", exc)
                    continue
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
        if aoa_thread is not None:
            aoa_thread.join(timeout=0.6)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="worker",
        description="sdr worker: energy detect + MUSIC; PUB iq/detect/aoa/status on 5556.",
    )
    add_source_args(parser)
    parser.add_argument(
        "--array",
        default=None,
        help=(
            "ArrayGeometry yaml "
            f"(replay default {DEFAULT_ARRAY_SIM}; live default {DEFAULT_ARRAY_HW})"
        ),
    )
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

    n_samp = int(args.n_samp)
    if n_samp == DEFAULT_N_SAMP:
        n_samp = LIVE_N_SAMP
    src = LiveSource(
        cmap,
        fc_hz=args.fc_hz,
        fs_hz=args.fs_hz,
        gain_db=args.gain_db,
        n_samp=n_samp,
    )
    return src, False, cmap


def load_estimator(array_path: Path) -> MusicEstimator:
    if not array_path.is_file():
        raise FileNotFoundError(f"array yaml not found: {array_path}")
    return MusicEstimator.from_array_yaml(array_path, REPO_ROOT)


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

    array_rel = args.array or (DEFAULT_ARRAY_SIM if replay else DEFAULT_ARRAY_HW)
    array_path = resolve_repo_path(array_rel)
    try:
        estimator = load_estimator(array_path)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        source.close()
        return 1

    M = source.frame.n_chan if replay else (cmap.M if isinstance(cmap, ChannelMap) else estimator.M)

    try:
        worker = Worker(
            source,
            pub_addr=args.pub,
            rep_addr=args.rep,
            replay=replay,
            M=M,
            estimator=estimator,
            save_stem=args.save,
        )
    except zmq.ZMQError as exc:
        source.close()
        print(
            f"error: cannot bind {args.pub} / {args.rep}: {exc}\n"
            "stop the other worker (Ctrl+C in that terminal) or pick --pub/--rep",
            file=sys.stderr,
        )
        return 1

    def _stop(*_args: object) -> None:
        worker.shutdown = True

    signal.signal(signal.SIGINT, _stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _stop)

    log.info(
        "PUB %s  REP %s  replay=%s  M=%s  array=%s  uncalibrated=%s",
        args.pub,
        args.rep,
        replay,
        M,
        array_path,
        worker.uncalibrated,
    )
    try:
        worker.run(auto_start=True)
    finally:
        worker.close()
    return 0 if worker.state != "error" else 1


if __name__ == "__main__":
    raise SystemExit(main())
