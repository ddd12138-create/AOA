"""Dataclasses matching frozen fields in docs/interfaces.md (schema_version=1)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from aoa.constants import SCHEMA_VERSION

GEO_FIX_NOTE = "single-station AOA must not populate GeoFix"


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _json_ready(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(v) for v in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


@dataclass
class GeoFix:
    """Single-station placeholder. valid must stay false."""

    valid: bool = False
    lat_deg: float | None = None
    lon_deg: float | None = None
    alt_m: float | None = None
    method: str = "none"
    station_ids: list[str] = field(default_factory=list)
    crs: str = "WGS84"
    note: str = GEO_FIX_NOTE

    def __post_init__(self) -> None:
        if self.valid:
            raise ValueError(GEO_FIX_NOTE)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": False,
            "lat_deg": None,
            "lon_deg": None,
            "alt_m": None,
            "method": self.method,
            "station_ids": list(self.station_ids),
            "crs": self.crs,
            "note": self.note,
        }


def invalid_geo_fix() -> GeoFix:
    return GeoFix()


@dataclass
class MusicPeak:
    theta_deg: float
    p_db: float

    def to_dict(self) -> dict[str, Any]:
        return {"theta_deg": float(self.theta_deg), "p_db": float(self.p_db)}


@dataclass
class MusicSpectrumSummary:
    grid_start_deg: float
    grid_stop_deg: float
    grid_step_deg: float
    n_peaks: int
    peaks: list[MusicPeak]

    def to_dict(self) -> dict[str, Any]:
        return {
            "grid_start_deg": float(self.grid_start_deg),
            "grid_stop_deg": float(self.grid_stop_deg),
            "grid_step_deg": float(self.grid_step_deg),
            "n_peaks": int(self.n_peaks),
            "peaks": [p.to_dict() for p in self.peaks],
        }


@dataclass
class IqRef:
    frame_id: int
    start_samp: int
    end_samp: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_id": int(self.frame_id),
            "start_samp": int(self.start_samp),
            "end_samp": int(self.end_samp),
        }


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

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        if self.dtype != "complex64":
            raise ValueError('dtype must be "complex64"')
        if self.layout != "channel_first":
            raise ValueError('layout must be "channel_first"')
        if self.endianness != "little":
            raise ValueError('endianness must be "little"')
        iq = np.asarray(self.iq)
        if iq.ndim != 2:
            raise ValueError("iq must have shape (n_chan, n_samp)")
        if iq.shape != (self.n_chan, self.n_samp):
            raise ValueError("n_chan/n_samp must match iq.shape")
        if len(self.channel_ids) != self.n_chan or len(self.element_ids) != self.n_chan:
            raise ValueError("channel_ids/element_ids length must equal n_chan")
        object.__setattr__(self, "iq", np.ascontiguousarray(iq, dtype=np.complex64))

    def meta_dict(self) -> dict[str, Any]:
        """IqFrame JSON header: every field except iq."""
        return {
            "schema_version": int(self.schema_version),
            "frame_id": int(self.frame_id),
            "timestamp_utc_ns": int(self.timestamp_utc_ns),
            "fc_hz": float(self.fc_hz),
            "fs_hz": float(self.fs_hz),
            "n_chan": int(self.n_chan),
            "n_samp": int(self.n_samp),
            "dtype": self.dtype,
            "layout": self.layout,
            "endianness": self.endianness,
            "channel_ids": [int(x) for x in self.channel_ids],
            "element_ids": [int(x) for x in self.element_ids],
        }

    @classmethod
    def from_npy_stem(cls, stem: str | Path) -> IqFrame:
        stem_path = Path(stem)
        iq = np.load(stem_path.with_suffix(".npy"), allow_pickle=False)
        meta_path = Path(str(stem_path) + ".meta.json")
        if not meta_path.exists():
            meta_path = stem_path.with_suffix(".meta.json")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return cls(
            schema_version=int(meta["schema_version"]),
            frame_id=int(meta["frame_id"]),
            timestamp_utc_ns=int(meta["timestamp_utc_ns"]),
            fc_hz=float(meta["fc_hz"]),
            fs_hz=float(meta["fs_hz"]),
            n_chan=int(meta["n_chan"]),
            n_samp=int(meta["n_samp"]),
            dtype=str(meta["dtype"]),
            layout=str(meta["layout"]),
            endianness=str(meta["endianness"]),
            channel_ids=[int(x) for x in meta["channel_ids"]],
            element_ids=[int(x) for x in meta["element_ids"]],
            iq=iq,
        )


@dataclass
class DetectionEvent:
    schema_version: int
    event_id: int
    timestamp_utc_ns: int
    fc_hz: float
    bw_hz: float
    snr_db: float
    burst_start_samp: int
    burst_end_samp: int
    burst_start_utc_ns: int
    burst_end_utc_ns: int
    iq_ref: IqRef
    band: str

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        if self.band not in ("900M", "2.4G", "5.8G"):
            raise ValueError('band must be "900M", "2.4G", or "5.8G"')
        if self.burst_end_samp < self.burst_start_samp:
            raise ValueError("burst_end_samp must be >= burst_start_samp")

    @classmethod
    def covering_frame(
        cls,
        frame: IqFrame,
        *,
        event_id: int = 1,
        snr_db: float = 20.0,
        bw_hz: float | None = None,
        band: str = "2.4G",
    ) -> DetectionEvent:
        end = int(frame.n_samp)
        return cls(
            schema_version=SCHEMA_VERSION,
            event_id=int(event_id),
            timestamp_utc_ns=int(frame.timestamp_utc_ns),
            fc_hz=float(frame.fc_hz),
            bw_hz=float(frame.fs_hz if bw_hz is None else bw_hz),
            snr_db=float(snr_db),
            burst_start_samp=0,
            burst_end_samp=end,
            burst_start_utc_ns=int(frame.timestamp_utc_ns),
            burst_end_utc_ns=int(frame.timestamp_utc_ns),
            iq_ref=IqRef(frame_id=int(frame.frame_id), start_samp=0, end_samp=end),
            band=band,
        )


@dataclass
class AoAResult:
    schema_version: int
    result_id: int
    timestamp_utc_ns: int
    detection_event_id: int
    azimuth_deg: float
    elevation_deg: float | None
    confidence: float
    music_spectrum_summary: MusicSpectrumSummary
    M: int
    element_ids: list[int]
    K_est: int
    geo_fix: GeoFix

    def to_dict(self) -> dict[str, Any]:
        """JSON payload for ZMQ topic `aoa` (frozen AoAResult fields only)."""
        az = float(self.azimuth_deg) % 360.0
        payload = {
            "schema_version": int(self.schema_version),
            "result_id": int(self.result_id),
            "timestamp_utc_ns": int(self.timestamp_utc_ns),
            "detection_event_id": int(self.detection_event_id),
            "azimuth_deg": az,
            "elevation_deg": None if self.elevation_deg is None else float(self.elevation_deg),
            "confidence": float(self.confidence),
            "music_spectrum_summary": self.music_spectrum_summary.to_dict(),
            "M": int(self.M),
            "element_ids": [int(x) for x in self.element_ids],
            "K_est": int(self.K_est),
            "geo_fix": self.geo_fix.to_dict(),
        }
        return _json_ready(payload)


@dataclass
class AoAOutput:
    """Worker-facing bundle.

    `result` is the frozen AoAResult (topic `aoa`).
    `uncalibrated` belongs on topic `status`, not inside AoAResult.
    """

    result: AoAResult
    uncalibrated: bool
    calib_status: str

    def aoa_json(self) -> dict[str, Any]:
        return self.result.to_dict()

    def status_fields(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "M": int(self.result.M),
            "uncalibrated": bool(self.uncalibrated),
        }
