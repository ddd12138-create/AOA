"""Known-source calib on golden θ=30°. Do not implement MUSIC in this test."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from aoa import DetectionEvent, IqFrame, MusicEstimator
from aoa.geometry import load_calib_file
from calib import (
    CalibError,
    MissingArrayRadiusError,
    NoBurstError,
    calibrate_replay,
    main,
)
from calib.io import dump_calib_yaml
from sdr.replay import load_replay, save_replay

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_STEM = ROOT / "tests" / "golden" / "theta30_m4"
SIM_ARRAY = ROOT / "configs" / "array_uca_m4_sim.yaml"
FIXTURE_ARRAY = ROOT / "configs" / "array_uca_m4_unset.yaml"
IDENTITY_CALIB = ROOT / "calib" / "identity.yaml"


def _angular_abs_err_deg(est: float, truth: float) -> float:
    return abs((float(est) - float(truth) + 180.0) % 360.0 - 180.0)


def _estimate_azimuth(frame: IqFrame, calib_path: Path) -> object:
    event = DetectionEvent.covering_frame(frame, snr_db=20.0, band="2.4G")
    estimator = MusicEstimator.from_array_yaml(SIM_ARRAY, ROOT, calib_path=calib_path)
    return estimator.estimate(frame, event)


def test_identity_yaml_still_means_uncalibrated():
    calib = load_calib_file(IDENTITY_CALIB)
    assert calib.status == "identity"
    assert calib.uncalibrated is True
    assert calib.fc_hz is None
    assert list(calib.gain_lin) == [1.0, 1.0, 1.0, 1.0]
    assert list(calib.phase_rad) == [0.0, 0.0, 0.0, 0.0]
    assert list(calib.channel_ids) == [0, 1, 2, 3]
    assert calib.M == 4
    assert calib.schema_version == 1


def test_calib_theta30_then_music_within_two_degrees(tmp_path: Path):
    out = tmp_path / "sim_theta30.yaml"
    calib = calibrate_replay(GOLDEN_STEM, 30.0, SIM_ARRAY)
    assert calib.status == "calibrated"
    assert calib.uncalibrated is False
    assert calib.schema_version == 1
    assert calib.M == 4
    assert list(calib.channel_ids) == [0, 1, 2, 3]
    assert calib.fc_hz == 2_400_000_000.0
    assert calib.gain_lin[0] == 1.0
    assert calib.phase_rad[0] == 0.0
    assert all(g > 0.0 for g in calib.gain_lin)

    written = Path(out)
    written.write_text(dump_calib_yaml(calib), encoding="utf-8")
    loaded = load_calib_file(written)
    assert loaded.status == "calibrated"
    assert loaded.uncalibrated is False

    frame = IqFrame.from_npy_stem(GOLDEN_STEM)
    out_est = _estimate_azimuth(frame, written)
    assert out_est.uncalibrated is False
    assert out_est.calib_status == "calibrated"
    assert out_est.status_fields()["uncalibrated"] is False
    assert _angular_abs_err_deg(out_est.result.azimuth_deg, 30.0) <= 2.0
    assert out_est.result.geo_fix.valid is False
    assert out_est.result.elevation_deg is None


def test_phase_injection_pulled_back(tmp_path: Path):
    """Multiply one channel by e^{jπ/2}; calib must restore 30°±2°."""
    base = load_replay(GOLDEN_STEM)
    iq = np.array(base.iq, copy=True)
    iq[1] *= np.exp(1j * np.pi / 2.0)
    rotated = replace(base, iq=np.ascontiguousarray(iq, dtype=np.complex64))
    stem = tmp_path / "theta30_phase_injected"
    save_replay(stem, rotated)

    calib = calibrate_replay(stem, 30.0, SIM_ARRAY)
    assert calib.status == "calibrated"
    assert calib.uncalibrated is False
    # Recovered hardware phase on the injected row, relative to channel 0.
    assert abs(((calib.phase_rad[1] - np.pi / 2.0 + np.pi) % (2.0 * np.pi)) - np.pi) <= 0.15

    yaml_path = tmp_path / "injected.yaml"
    yaml_path.write_text(dump_calib_yaml(calib), encoding="utf-8")

    frame = IqFrame(
        schema_version=1,
        frame_id=int(rotated.frame_id),
        timestamp_utc_ns=int(rotated.timestamp_utc_ns),
        fc_hz=float(rotated.fc_hz),
        fs_hz=float(rotated.fs_hz),
        n_chan=int(rotated.n_chan),
        n_samp=int(rotated.n_samp),
        dtype="complex64",
        layout="channel_first",
        endianness="little",
        channel_ids=list(rotated.channel_ids),
        element_ids=list(rotated.element_ids),
        iq=rotated.iq,
    )
    out_est = _estimate_azimuth(frame, yaml_path)
    assert out_est.uncalibrated is False
    assert out_est.calib_status == "calibrated"
    assert _angular_abs_err_deg(out_est.result.azimuth_deg, 30.0) <= 2.0


def test_rm_null_refuses_calibration():
    with pytest.raises(MissingArrayRadiusError, match="R_m"):
        calibrate_replay(GOLDEN_STEM, 30.0, FIXTURE_ARRAY)


def test_no_detect_event_fails(tmp_path: Path):
    frame = load_replay(GOLDEN_STEM)
    silent = replace(frame, fc_hz=1.2e9)
    stem = tmp_path / "oob_fc"
    save_replay(stem, silent)
    with pytest.raises(NoBurstError, match="DetectionEvent"):
        calibrate_replay(stem, 30.0, SIM_ARRAY)


def test_cli_writes_calibrated_and_refuses_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "cli_calib.yaml"
    rc = main(
        [
            "--replay",
            str(GOLDEN_STEM),
            "--theta-deg",
            "30",
            "--array",
            str(SIM_ARRAY),
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    loaded = load_calib_file(out)
    assert loaded.status == "calibrated"
    assert loaded.uncalibrated is False

    rc_id = main(
        [
            "--replay",
            str(GOLDEN_STEM),
            "--theta-deg",
            "30",
            "--array",
            str(SIM_ARRAY),
            "--out",
            str(IDENTITY_CALIB),
        ]
    )
    assert rc_id == 1
    still = load_calib_file(IDENTITY_CALIB)
    assert still.status == "identity"
    assert still.uncalibrated is True


def test_cli_rm_null_exits_nonzero():
    rc = main(
        [
            "--replay",
            str(GOLDEN_STEM),
            "--theta-deg",
            "30",
            "--array",
            str(FIXTURE_ARRAY),
            "--out",
            str(Path("calib") / "should_not_write.yaml"),
        ]
    )
    assert rc == 1
    assert not (ROOT / "calib" / "should_not_write.yaml").exists()


def test_writer_rejects_identity_status():
    from aoa.geometry import CalibFile

    ident = CalibFile(
        schema_version=1,
        M=4,
        channel_ids=(0, 1, 2, 3),
        gain_lin=(1.0, 1.0, 1.0, 1.0),
        phase_rad=(0.0, 0.0, 0.0, 0.0),
        status="identity",
        fc_hz=None,
    )
    with pytest.raises(CalibError, match="calibrated"):
        dump_calib_yaml(ident)
