"""DetectionEvent / IqRef fields match docs/interfaces.md (schema_version=1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SCHEMA_VERSION = 1
BAND_IDS = ("900M", "2.4G", "5.8G")


@dataclass(frozen=True)
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


@dataclass(frozen=True)
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
        if self.band not in BAND_IDS:
            raise ValueError('band must be "900M", "2.4G", or "5.8G"')
        if self.burst_end_samp < self.burst_start_samp:
            raise ValueError("burst_end_samp must be >= burst_start_samp")
        if self.iq_ref.start_samp != self.burst_start_samp:
            raise ValueError("iq_ref.start_samp must equal burst_start_samp")
        if self.iq_ref.end_samp != self.burst_end_samp:
            raise ValueError("iq_ref.end_samp must equal burst_end_samp")

    def to_dict(self) -> dict[str, Any]:
        """ZMQ topic `detect` payload. No IQ samples."""
        return {
            "schema_version": int(self.schema_version),
            "event_id": int(self.event_id),
            "timestamp_utc_ns": int(self.timestamp_utc_ns),
            "fc_hz": float(self.fc_hz),
            "bw_hz": float(self.bw_hz),
            "snr_db": float(self.snr_db),
            "burst_start_samp": int(self.burst_start_samp),
            "burst_end_samp": int(self.burst_end_samp),
            "burst_start_utc_ns": int(self.burst_start_utc_ns),
            "burst_end_utc_ns": int(self.burst_end_utc_ns),
            "iq_ref": self.iq_ref.to_dict(),
            "band": str(self.band),
        }
