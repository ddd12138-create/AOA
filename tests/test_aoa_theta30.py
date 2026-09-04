"""θ=30° MUSIC acceptance. Do not implement peak search in this test."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from aoa import (
    DetectionEvent,
    IqFrame,
    MissingArrayRadiusError,
    MusicEstimator,
)

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_STEM = ROOT / "tests" / "golden" / "theta30_m4"
SIM_ARRAY = ROOT / "configs" / "array_uca_m4_sim.yaml"
FIXTURE_ARRAY = ROOT / "configs" / "array_uca_m4.yaml"
IDENTITY_CALIB = ROOT / "calib" / "identity.yaml"


def _angular_abs_err_deg(est: float, truth: float) -> float:
    return abs((float(est) - float(truth) + 180.0) % 360.0 - 180.0)


def test_aoa_theta30_within_two_degrees():
    """Replay tests/golden/theta30_m4; expect |azimuth_deg - 30| <= 2.

    Golden files are produced by sim/. This is algorithm regression,
    not the field 5° RMS spec. Do not call MUSIC from the test body.
    """
    frame = IqFrame.from_npy_stem(GOLDEN_STEM)
    assert frame.n_chan == 4
    assert frame.n_samp >= 1024
    assert frame.iq.dtype == np.complex64
    assert frame.iq.shape == (frame.n_chan, frame.n_samp)

    event = DetectionEvent.covering_frame(frame, snr_db=20.0, band="2.4G")
    estimator = MusicEstimator.from_array_yaml(SIM_ARRAY, ROOT, calib_path=IDENTITY_CALIB)
    assert estimator.uncalibrated is True
    assert estimator.calib.status == "identity"

    out = estimator.estimate(frame, event)
    result = out.result
    payload = out.aoa_json()

    assert _angular_abs_err_deg(result.azimuth_deg, 30.0) <= 2.0
    assert result.elevation_deg is None
    assert payload["elevation_deg"] is None
    assert result.geo_fix.valid is False
    assert payload["geo_fix"]["valid"] is False
    assert result.M == 4
    assert result.element_ids == [1, 3, 5, 7]
    assert result.K_est in (1, 2)
    assert result.schema_version == 1
    assert 0.0 <= result.azimuth_deg < 360.0
    assert 0.0 <= result.confidence <= 1.0

    summary = payload["music_spectrum_summary"]
    assert summary["grid_start_deg"] == 0
    assert summary["grid_stop_deg"] == 360
    assert summary["grid_step_deg"] == 0.5
    assert summary["n_peaks"] >= 1
    assert "theta_deg" in summary["peaks"][0] and "p_db" in summary["peaks"][0]

    assert out.uncalibrated is True
    assert out.calib_status == "identity"
    assert "uncalibrated" not in payload
    assert out.status_fields()["uncalibrated"] is True

    meta = json.loads(Path(str(GOLDEN_STEM) + ".meta.json").read_text(encoding="utf-8"))
    assert "iq" not in meta


def test_rm_null_refuses_azimuth():
    """Fixture geometry keeps R_m null; estimator must not guess a radius."""
    frame = IqFrame.from_npy_stem(GOLDEN_STEM)
    event = DetectionEvent.covering_frame(frame, snr_db=20.0, band="2.4G")
    estimator = MusicEstimator.from_array_yaml(FIXTURE_ARRAY, ROOT, calib_path=IDENTITY_CALIB)
    with pytest.raises(MissingArrayRadiusError, match="R_m"):
        estimator.estimate(frame, event)
