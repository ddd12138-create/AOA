"""IqFrame: multi-channel baseband snapshot. Fields match docs/interfaces.md."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any

import numpy as np

from sdr.errors import SdrError

SCHEMA_VERSION = 1
IQ_DTYPE_NAME = "complex64"
IQ_LAYOUT = "channel_first"
IQ_ENDIANNESS = "little"

HEADER_KEYS = (
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


def _require_little_endian() -> None:
    if sys.byteorder != "little":
        raise SdrError("IqFrame endianness must be little; this host is not little-endian")


@dataclass
class IqFrame:
    schema_version: int
    frame_id: int
    timestamp_utc_ns: int
    fc_hz: float
    fs_hz: float
    n_chan: int
    n_samp: int
    dtype: str
    layout: str
    endianness: str
    channel_ids: list[int]
    element_ids: list[int]
    iq: np.ndarray

    def to_header(self) -> dict[str, Any]:
        """JSON header: every IqFrame field except iq."""
        return {
            "schema_version": int(self.schema_version),
            "frame_id": int(self.frame_id),
            "timestamp_utc_ns": int(self.timestamp_utc_ns),
            "fc_hz": float(self.fc_hz),
            "fs_hz": float(self.fs_hz),
            "n_chan": int(self.n_chan),
            "n_samp": int(self.n_samp),
            "dtype": str(self.dtype),
            "layout": str(self.layout),
            "endianness": str(self.endianness),
            "channel_ids": [int(x) for x in self.channel_ids],
            "element_ids": [int(x) for x in self.element_ids],
        }

    def header_json(self) -> str:
        return json.dumps(self.to_header(), ensure_ascii=False, separators=(",", ":"))

    def iq_bytes(self) -> bytes:
        """complex64 C-order payload; length n_chan * n_samp * 8."""
        iq = np.ascontiguousarray(self.iq, dtype=np.complex64)
        return iq.tobytes(order="C")

    def zmq_parts(self) -> list[bytes]:
        """PUB multipart after the topic frame: [header_json, raw_iq]."""
        return [self.header_json().encode("utf-8"), self.iq_bytes()]


def validate_iq_array(iq: np.ndarray, n_chan: int, n_samp: int) -> np.ndarray:
    _require_little_endian()
    if not isinstance(iq, np.ndarray):
        raise SdrError("iq must be a numpy ndarray")
    if iq.ndim != 2:
        raise SdrError(f"iq must be 2-D (n_chan, n_samp), got shape {iq.shape}")
    if iq.shape != (n_chan, n_samp):
        raise SdrError(f"iq shape {iq.shape} != (n_chan, n_samp)=({n_chan}, {n_samp})")
    if iq.dtype != np.complex64:
        raise SdrError(f"iq dtype must be complex64, got {iq.dtype}")
    if not iq.flags["C_CONTIGUOUS"]:
        iq = np.ascontiguousarray(iq, dtype=np.complex64)
    return iq


def frame_from_header_and_iq(header: dict[str, Any], iq: np.ndarray) -> IqFrame:
    missing = [k for k in HEADER_KEYS if k not in header]
    if missing:
        raise SdrError(f"IqFrame header missing fields: {missing}")
    if int(header["schema_version"]) != SCHEMA_VERSION:
        raise SdrError(f"schema_version must be {SCHEMA_VERSION}")
    if str(header["dtype"]) != IQ_DTYPE_NAME:
        raise SdrError(f'dtype must be "{IQ_DTYPE_NAME}"')
    if str(header["layout"]) != IQ_LAYOUT:
        raise SdrError(f'layout must be "{IQ_LAYOUT}"')
    if str(header["endianness"]) != IQ_ENDIANNESS:
        raise SdrError(f'endianness must be "{IQ_ENDIANNESS}"')

    n_chan = int(header["n_chan"])
    n_samp = int(header["n_samp"])
    if n_chan < 1 or n_samp < 1:
        raise SdrError("n_chan and n_samp must be >= 1")

    channel_ids = [int(x) for x in header["channel_ids"]]
    element_ids = [int(x) for x in header["element_ids"]]
    if len(channel_ids) != n_chan or len(element_ids) != n_chan:
        raise SdrError("channel_ids and element_ids length must equal n_chan")

    iq = validate_iq_array(iq, n_chan, n_samp)
    return IqFrame(
        schema_version=SCHEMA_VERSION,
        frame_id=int(header["frame_id"]),
        timestamp_utc_ns=int(header["timestamp_utc_ns"]),
        fc_hz=float(header["fc_hz"]),
        fs_hz=float(header["fs_hz"]),
        n_chan=n_chan,
        n_samp=n_samp,
        dtype=IQ_DTYPE_NAME,
        layout=IQ_LAYOUT,
        endianness=IQ_ENDIANNESS,
        channel_ids=channel_ids,
        element_ids=element_ids,
        iq=iq,
    )


def make_iq_frame(
    *,
    frame_id: int,
    timestamp_utc_ns: int,
    fc_hz: float,
    fs_hz: float,
    channel_ids: list[int],
    element_ids: list[int],
    iq: np.ndarray,
) -> IqFrame:
    n_chan, n_samp = int(iq.shape[0]), int(iq.shape[1]) if iq.ndim == 2 else (0, 0)
    return frame_from_header_and_iq(
        {
            "schema_version": SCHEMA_VERSION,
            "frame_id": frame_id,
            "timestamp_utc_ns": timestamp_utc_ns,
            "fc_hz": fc_hz,
            "fs_hz": fs_hz,
            "n_chan": n_chan,
            "n_samp": n_samp,
            "dtype": IQ_DTYPE_NAME,
            "layout": IQ_LAYOUT,
            "endianness": IQ_ENDIANNESS,
            "channel_ids": channel_ids,
            "element_ids": element_ids,
        },
        iq,
    )
