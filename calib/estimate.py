"""Narrowband known-source gain/phase vs channel 0. No MUSIC, no UHD."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import numpy as np

from aoa.constants import SCHEMA_VERSION
from aoa.geometry import (
    ArrayGeometry,
    CalibFile,
    load_array_geometry,
    require_radius_m,
    steering_matrix,
)
from detect import detect_frame
from sdr.replay import load_replay

from calib.errors import CalibError, NoBurstError


class IqFrameLike(Protocol):
    fc_hz: float
    n_chan: int
    n_samp: int
    channel_ids: list[int]
    element_ids: list[int]
    iq: np.ndarray


def relative_gain_phase(iq_burst: np.ndarray, a_theta: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Estimate gain_lin and phase_rad of γ relative to row 0.

    Model: x ≈ (γ ⊙ a(θ)) s. CalibFile weights multiply a(θ) rows, so
    γ_rel[m] = E[x_m x_0*] / E[|x_0|^2] / (a_m / a_0).
    """
    x = np.asarray(iq_burst)
    a = np.asarray(a_theta, dtype=np.complex128).reshape(-1)
    if x.ndim != 2:
        raise CalibError("burst IQ must have shape (M, N)")
    m, n = x.shape
    if a.size != m:
        raise CalibError("steering vector length must equal channel count")
    if n < m:
        raise CalibError("burst is shorter than M snapshots")
    if not np.isfinite(a).all() or np.any(np.abs(a) < 1e-15):
        raise CalibError("a(θ) has a near-zero element; check ArrayGeometry")

    x64 = np.ascontiguousarray(x, dtype=np.complex128)
    ref = x64[0]
    denom = float(np.mean(np.abs(ref) ** 2))
    if not np.isfinite(denom) or denom <= 0.0:
        raise CalibError("reference channel 0 has no energy on the burst")
    observed_rel = np.mean(x64 * np.conj(ref)[None, :], axis=1) / denom
    a_rel = a / a[0]
    weights = observed_rel / a_rel
    # Exact identity on the reference row.
    weights = weights / weights[0]
    gain = np.abs(weights).astype(np.float64)
    phase = np.angle(weights).astype(np.float64)
    gain[0] = 1.0
    phase[0] = 0.0
    return gain, phase


def calibrate_known_source(
    frame: IqFrameLike,
    theta_deg: float,
    geometry: ArrayGeometry,
    *,
    bands_path: str | Path | None = None,
) -> CalibFile:
    """Cut a detect burst and fit CalibFile at the known array azimuth."""
    require_radius_m(geometry)
    if not np.isfinite(theta_deg):
        raise CalibError("theta_deg must be a finite array-frame azimuth in degrees")
    if int(frame.n_chan) != int(geometry.M):
        raise CalibError("IqFrame.n_chan must match ArrayGeometry.M")
    if list(frame.element_ids) != list(geometry.element_ids):
        raise CalibError("IqFrame.element_ids must match ArrayGeometry.element_ids")
    if len(frame.channel_ids) != int(frame.n_chan):
        raise CalibError("channel_ids length must equal n_chan")

    events = detect_frame(frame, bands_path=bands_path)
    if not events:
        raise NoBurstError(
            "detect produced no DetectionEvent; refusing known-source calibration"
        )
    event = events[0]
    start = int(event.burst_start_samp)
    end = int(event.burst_end_samp)
    if start < 0 or end > int(frame.n_samp) or end <= start:
        raise CalibError("DetectionEvent burst range is empty or out of bounds")
    burst = np.asarray(frame.iq)[:, start:end]
    a_theta = steering_matrix([float(theta_deg)], geometry, float(frame.fc_hz), calib=None)[:, 0]
    gain, phase = relative_gain_phase(burst, a_theta)
    return CalibFile(
        schema_version=SCHEMA_VERSION,
        M=int(geometry.M),
        channel_ids=tuple(int(x) for x in frame.channel_ids),
        gain_lin=tuple(float(x) for x in gain),
        phase_rad=tuple(float(x) for x in phase),
        status="calibrated",
        fc_hz=float(frame.fc_hz),
    )


def calibrate_replay(
    replay_stem: str | Path,
    theta_deg: float,
    array_yaml: str | Path,
    *,
    bands_path: str | Path | None = None,
) -> CalibFile:
    geometry = load_array_geometry(array_yaml)
    frame = load_replay(replay_stem)
    return calibrate_known_source(frame, theta_deg, geometry, bands_path=bands_path)
