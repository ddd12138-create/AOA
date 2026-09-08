"""IqFrame → DetectionEvent. Narrowband energy + burst cut; no IQ copy."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import numpy as np

from detect.bands import BandSpec, classify_band, load_bands
from detect.energy import burst_snr_db, scan_frame
from detect.errors import DetectError
from detect.types import SCHEMA_VERSION, DetectionEvent, IqRef


class IqFrameLike(Protocol):
    frame_id: int
    timestamp_utc_ns: int
    fc_hz: float
    fs_hz: float
    n_chan: int
    n_samp: int
    iq: np.ndarray


def _samp_to_utc_ns(frame_utc_ns: int, samp: int, fs_hz: float) -> int:
    if fs_hz <= 0.0:
        raise DetectError("fs_hz must be > 0")
    return int(frame_utc_ns + round(float(samp) * 1.0e9 / float(fs_hz)))


def _min_burst_samp(n_chan: int, n_samp: int) -> int:
    # MUSIC needs >= M snapshots; keep a small floor so AOA is not fed crumbs.
    return min(int(n_samp), max(32, int(n_chan)))


class EnergyBurstDetector:
    """Energy detector for the three bands in configs/bands.yaml."""

    def __init__(self, bands_path: str | Path | None = None) -> None:
        self._bands: tuple[BandSpec, ...] = load_bands(bands_path)

    def detect(self, frame: IqFrameLike, *, first_event_id: int = 1) -> list[DetectionEvent]:
        band = classify_band(float(frame.fc_hz), self._bands)
        if band is None:
            return []

        n_chan = int(frame.n_chan)
        n_samp = int(frame.n_samp)
        if n_chan < 1 or n_samp < 16:
            return []
        iq = np.asarray(frame.iq)
        if iq.ndim != 2 or iq.shape != (n_chan, n_samp):
            raise DetectError("IqFrame.iq shape must equal (n_chan, n_samp)")

        occ, spans = scan_frame(iq, float(frame.fs_hz), n_chan, n_samp)
        if occ is None or not spans:
            return []

        min_len = _min_burst_samp(n_chan, n_samp)
        events: list[DetectionEvent] = []
        event_id = int(first_event_id)
        fs = float(frame.fs_hz)
        t0 = int(frame.timestamp_utc_ns)
        fc = float(frame.fc_hz) + float(occ.offset_hz)
        bw = min(float(occ.bw_hz), fs)
        frame_id = int(frame.frame_id)

        for span in spans:
            start = int(span.start_samp)
            end = int(span.end_samp)
            if end - start < min_len:
                continue
            start_utc = _samp_to_utc_ns(t0, start, fs)
            end_utc = _samp_to_utc_ns(t0, end, fs)
            snr = burst_snr_db(
                iq,
                start,
                end,
                spectral_snr_db=occ.snr_db,
                nfft=int(occ.bin_mask.size),
            )
            events.append(
                DetectionEvent(
                    schema_version=SCHEMA_VERSION,
                    event_id=event_id,
                    timestamp_utc_ns=start_utc,
                    fc_hz=fc,
                    bw_hz=bw,
                    snr_db=float(snr),
                    burst_start_samp=start,
                    burst_end_samp=end,
                    burst_start_utc_ns=start_utc,
                    burst_end_utc_ns=end_utc,
                    iq_ref=IqRef(frame_id=frame_id, start_samp=start, end_samp=end),
                    band=band,
                )
            )
            event_id += 1
        return events


_DEFAULT: EnergyBurstDetector | None = None


def default_detector() -> EnergyBurstDetector:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = EnergyBurstDetector()
    return _DEFAULT


def detect_frame(
    frame: IqFrameLike,
    *,
    first_event_id: int = 1,
    bands_path: str | Path | None = None,
) -> list[DetectionEvent]:
    """Public entry: zero or more DetectionEvents. Empty means idle, not error."""
    if bands_path is not None:
        return EnergyBurstDetector(bands_path).detect(frame, first_event_id=first_event_id)
    return default_detector().detect(frame, first_event_id=first_event_id)
