"""ZMQ envelope helpers. Display-side parse only — no MUSIC / UHD."""

from __future__ import annotations

import json
import math
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

SCHEMA_VERSION = 1
DEFAULT_SUB = "tcp://127.0.0.1:5556"
DEFAULT_CMD = "tcp://127.0.0.1:5557"
TOPICS = ("iq", "detect", "aoa", "status")

_IQ_HEADER_KEYS = (
    "schema_version",
    "frame_id",
    "timestamp_utc_ns",
    "fc_hz",
    "fs_hz",
    "n_chan",
    "n_samp",
    "dtype",
    "layout",
    "endianness",
    "channel_ids",
    "element_ids",
)


def derive_command_endpoint(sub_endpoint: str) -> str:
    """REP command port: same host as SUB, port + 1 (5556 → 5557)."""
    raw = (sub_endpoint or "").strip() or DEFAULT_SUB
    parts = urlsplit(raw)
    if parts.scheme != "tcp" or not parts.hostname or parts.port is None:
        return DEFAULT_CMD
    return urlunsplit((parts.scheme, f"{parts.hostname}:{parts.port + 1}", "", "", ""))


def decode_json_bytes(raw: bytes | str) -> dict[str, Any] | None:
    if isinstance(raw, str):
        text = raw
    else:
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def topic_of(frames: list[bytes]) -> str | None:
    if not frames:
        return None
    first = frames[0]
    if isinstance(first, bytes):
        try:
            name = first.decode("utf-8")
        except UnicodeDecodeError:
            return None
    else:
        name = str(first)
    return name if name in TOPICS else None


def as_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return float(value)
    return None


def wrap_azimuth_deg(value: Any) -> float | None:
    az = as_float(value)
    if az is None:
        return None
    return az % 360.0


def geo_fix_valid(msg: dict[str, Any]) -> bool:
    geo = msg.get("geo_fix")
    return isinstance(geo, dict) and geo.get("valid") is True


def summarize_iq(header: dict[str, Any], blob: bytes) -> dict[str, Any]:
    """Cheap per-channel RMS + a short |IQ| trace. Not a DF algorithm."""
    meta = {key: header.get(key) for key in _IQ_HEADER_KEYS}
    n_chan = int(header["n_chan"]) if isinstance(header.get("n_chan"), int) else 0
    n_samp = int(header["n_samp"]) if isinstance(header.get("n_samp"), int) else 0
    channel_ids = header.get("channel_ids") if isinstance(header.get("channel_ids"), list) else []
    element_ids = header.get("element_ids") if isinstance(header.get("element_ids"), list) else []
    rms_lin: list[float] = []
    mag_trace: list[float] = []
    expected = n_chan * n_samp * 8
    ok_dtype = header.get("dtype") in (None, "complex64")
    ok_layout = header.get("layout") in (None, "channel_first")
    if (
        blob
        and ok_dtype
        and ok_layout
        and n_chan > 0
        and n_samp > 0
        and len(blob) >= expected
    ):
        import numpy as np

        iq = np.frombuffer(blob, dtype=np.complex64, count=n_chan * n_samp).reshape(
            n_chan, n_samp
        )
        power = np.mean(iq.real * iq.real + iq.imag * iq.imag, axis=1)
        rms_lin = [float(x) for x in np.sqrt(power)]
        mag = np.abs(iq[0])
        if mag.size > 256:
            mag = mag[:: max(1, mag.size // 256)][:256]
        mag_trace = [float(x) for x in mag]
    return {
        "header": meta,
        "n_chan": n_chan,
        "n_samp": n_samp,
        "channel_ids": channel_ids,
        "element_ids": element_ids,
        "rms_lin": rms_lin,
        "mag_trace": mag_trace,
    }


def format_hz(value: Any) -> str:
    hz = as_float(value)
    if hz is None:
        return "—"
    if hz >= 1e9:
        return f"{hz / 1e9:.6g} GHz"
    if hz >= 1e6:
        return f"{hz / 1e6:.6g} MHz"
    if hz >= 1e3:
        return f"{hz / 1e3:.6g} kHz"
    return f"{hz:.6g} Hz"


def format_db(lin: float) -> str:
    if lin <= 0.0:
        return "-inf dB"
    return f"{20.0 * math.log10(lin):.1f} dB"


_SAFE_DETAIL = re.compile(r"[^\x20-\x7E\u4e00-\u9fff]+")


def status_detail(msg: dict[str, Any]) -> str:
    detail = msg.get("detail")
    if not isinstance(detail, str):
        return ""
    return _SAFE_DETAIL.sub(" ", detail).strip()
