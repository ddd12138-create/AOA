"""Local check: worker --replay theta30_m4 publishes AoA near 30° (host polar input)."""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import zmq

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_STEM = "tests/golden/theta30_m4"
FIXTURE_ARRAY = "configs/array_uca_m4_unset.yaml"
HW_ARRAY = "configs/array_uca_m4.yaml"
WORKER = ROOT / "scripts" / "worker.py"


def _angular_abs_err_deg(est: float, truth: float) -> float:
    return abs((float(est) - float(truth) + 180.0) % 360.0 - 180.0)


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


def _ephemeral_endpoints() -> tuple[str, str]:
    return f"tcp://127.0.0.1:{_free_port()}", f"tcp://127.0.0.1:{_free_port()}"


def _collect(
    pub_addr: str, timeout_s: float
) -> tuple[list[dict], list[dict], list[dict], int]:
    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.setsockopt(zmq.LINGER, 0)
    sub.setsockopt(zmq.RCVTIMEO, 150)
    sub.setsockopt(zmq.SUBSCRIBE, b"aoa")
    sub.setsockopt(zmq.SUBSCRIBE, b"status")
    sub.setsockopt(zmq.SUBSCRIBE, b"detect")
    sub.setsockopt(zmq.SUBSCRIBE, b"iq")
    sub.connect(pub_addr)
    time.sleep(0.35)
    aoas: list[dict] = []
    statuses: list[dict] = []
    detects: list[dict] = []
    iq_n = 0
    deadline = time.monotonic() + timeout_s
    try:
        while time.monotonic() < deadline:
            try:
                frames = sub.recv_multipart()
            except zmq.Again:
                continue
            if len(frames) < 2:
                continue
            topic = frames[0].decode("utf-8")
            if topic == "iq":
                iq_n += 1
                continue
            body = json.loads(frames[1].decode("utf-8"))
            if not isinstance(body, dict):
                continue
            if topic == "aoa":
                aoas.append(body)
            elif topic == "status":
                statuses.append(body)
            elif topic == "detect":
                detects.append(body)
    finally:
        sub.close(0)
        ctx.term()
    return aoas, statuses, detects, iq_n


def _spawn_worker(*extra: str) -> tuple[subprocess.Popen, str]:
    pub, rep = _ephemeral_endpoints()
    cmd = [
        sys.executable,
        str(WORKER),
        "--replay",
        GOLDEN_STEM,
        "--pub",
        pub,
        "--rep",
        rep,
        *extra,
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return proc, pub


def _stop(proc: subprocess.Popen) -> tuple[str, str]:
    if proc.poll() is None:
        proc.terminate()
        try:
            stdout, stderr = proc.communicate(timeout=4)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate(timeout=4)
        return stdout, stderr
    stdout, stderr = proc.communicate(timeout=4)
    return stdout, stderr


def test_worker_replay_theta30_aoa_topic_near_30():
    """`--replay` defaults to sim yaml. Host polar uses this azimuth_deg (~30°)."""
    proc, pub = _spawn_worker()
    try:
        time.sleep(0.4)
        assert proc.poll() is None, _stop(proc)[1]
        aoas, statuses, detects, iq_n = _collect(pub, timeout_s=4.0)
        assert statuses, "no status topic (host would stay 未连接)"
        assert iq_n > 0, "expected iq topic during sim replay"
        assert detects, "expected detect topic before aoa"
        assert aoas, "no aoa topic (host polar would not move)"

        last = aoas[-1]
        az = float(last["azimuth_deg"])
        assert _angular_abs_err_deg(az, 30.0) <= 2.0, az
        assert last["elevation_deg"] is None
        assert last["geo_fix"]["valid"] is False
        assert last["M"] == 4
        assert "uncalibrated" not in last

        status = statuses[-1]
        assert status["uncalibrated"] is True
        assert status["replay"] is True
        assert status["state"] == "running"
        assert status["M"] == 4
    finally:
        _stop(proc)


def test_worker_hardware_array_rm_null_no_aoa_topic():
    """Hardware yaml R_m is null: iq/detect still PUB; no aoa; running + detail."""
    proc, pub = _spawn_worker("--array", FIXTURE_ARRAY)
    try:
        time.sleep(0.4)
        aoas, statuses, detects, iq_n = _collect(pub, timeout_s=3.0)
        assert statuses, "expected status while streaming without R_m"
        running = next((s for s in statuses if s.get("state") == "running"), statuses[-1])
        assert running["state"] == "running"
        assert running["state"] != "error"
        assert "R_m" in str(running.get("detail") or "")
        assert running["uncalibrated"] is True
        assert iq_n > 0, "missing R_m must not stop iq PUB"
        assert detects, "missing R_m must still PUB detect when a burst exists"
        assert aoas == []
        assert all(s.get("state") != "error" for s in statuses)
    finally:
        _stop(proc)


def test_worker_hardware_array_rm_set_aoa_uncalibrated():
    """R_m=0.06 unblocks aoa; identity.yaml still marks UNCALIBRATED. Not a 30° check."""
    proc, pub = _spawn_worker("--array", HW_ARRAY)
    try:
        time.sleep(0.4)
        assert proc.poll() is None, _stop(proc)[1]
        aoas, statuses, detects, iq_n = _collect(pub, timeout_s=4.0)
        assert statuses, "expected status with hardware array yaml"
        assert iq_n > 0
        assert detects, "golden burst should still PUB detect"
        assert aoas, "R_m=0.06 must allow aoa PUB"

        last = aoas[-1]
        assert last["elevation_deg"] is None
        assert last["geo_fix"]["valid"] is False
        assert last["M"] == 4
        assert "uncalibrated" not in last
        assert last["geo_fix"].get("lat_deg") is None
        assert last["geo_fix"].get("lon_deg") is None

        status = statuses[-1]
        assert status["uncalibrated"] is True
        assert status["state"] == "running"
        assert "R_m" not in str(status.get("detail") or "")
    finally:
        _stop(proc)


def test_worker_replay_save_writes_iqframe_pair():
    scratch = ROOT / "tests" / "_scratch" / uuid.uuid4().hex
    scratch.mkdir(parents=True, exist_ok=True)
    stem = scratch / "live_frame"
    proc, pub = _spawn_worker("--save", str(stem))
    try:
        time.sleep(0.4)
        assert proc.poll() is None, _stop(proc)[1]
        _collect(pub, timeout_s=2.0)
        npy = stem.with_suffix(".npy")
        meta = Path(str(stem) + ".meta.json")
        assert npy.is_file(), npy
        assert meta.is_file(), meta
        header = json.loads(meta.read_text(encoding="utf-8"))
        assert "iq" not in header
        assert header["n_chan"] == 4
        assert header["element_ids"] == [1, 3, 5, 7]
        assert header["channel_ids"] == [0, 1, 2, 3]
        assert header["dtype"] == "complex64"
        assert header["layout"] == "channel_first"
        assert header["endianness"] == "little"
    finally:
        _stop(proc)
        shutil.rmtree(scratch, ignore_errors=True)
