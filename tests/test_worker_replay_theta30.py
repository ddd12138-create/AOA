"""Local check: worker --replay theta30_m4 publishes AoA near 30° (host polar input)."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import zmq

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_STEM = "tests/golden/theta30_m4"
FIXTURE_ARRAY = "configs/array_uca_m4.yaml"
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


def _collect(pub_addr: str, timeout_s: float) -> tuple[list[dict], list[dict]]:
    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.setsockopt(zmq.LINGER, 0)
    sub.setsockopt(zmq.RCVTIMEO, 150)
    sub.setsockopt(zmq.SUBSCRIBE, b"aoa")
    sub.setsockopt(zmq.SUBSCRIBE, b"status")
    sub.connect(pub_addr)
    time.sleep(0.35)
    aoas: list[dict] = []
    statuses: list[dict] = []
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
            body = json.loads(frames[1].decode("utf-8"))
            if not isinstance(body, dict):
                continue
            if topic == "aoa":
                aoas.append(body)
            elif topic == "status":
                statuses.append(body)
    finally:
        sub.close(0)
        ctx.term()
    return aoas, statuses


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
        aoas, statuses = _collect(pub, timeout_s=4.0)
        assert statuses, "no status topic (host would stay 未连接)"
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


def test_worker_hardware_array_rm_null_refuses_aoa():
    """configs/array_uca_m4.yaml keeps R_m null: no azimuth, status.state=error."""
    proc, pub = _spawn_worker("--array", FIXTURE_ARRAY)
    try:
        time.sleep(0.4)
        aoas, statuses = _collect(pub, timeout_s=3.0)
        assert statuses, "expected status error when R_m is null"
        err = next((s for s in statuses if s.get("state") == "error"), statuses[-1])
        assert err["state"] == "error"
        assert "R_m" in str(err.get("detail") or "")
        assert err["uncalibrated"] is True
        assert aoas == []
    finally:
        _stop(proc)
