"""Synthetic UCA snapshots with a known arrival angle (no MUSIC peak picking)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from aoa.constants import C_MPS, SCHEMA_VERSION
from aoa.geometry import ArrayGeometry, load_array_geometry, steering_matrix
from aoa.types import IqFrame

DEFAULT_THETA_DEG = 30.0
DEFAULT_SNR_DB = 20.0
DEFAULT_N_SAMP = 2048
DEFAULT_FC_HZ = 2_400_000_000.0
DEFAULT_FS_HZ = 1_000_000.0
DEFAULT_SEED = 30
DEFAULT_TONE_CYCLES_PER_SAMPLE = 0.01


def uca_snapshot(
    geometry: ArrayGeometry,
    theta_deg: float,
    *,
    fc_hz: float,
    n_samp: int,
    snr_db: float,
    rng: np.random.Generator,
    tone_cycles_per_sample: float = DEFAULT_TONE_CYCLES_PER_SAMPLE,
) -> np.ndarray:
    """x(n) = a(θ) s(n) + noise, complex64, shape (M, N).

    Uses the physical UCA manifold (identity weights). SNR is per-element,
    since |a_m| = 1.
    """
    a = steering_matrix([theta_deg], geometry, fc_hz, calib=None, c_mps=C_MPS)[:, 0]
    n = np.arange(int(n_samp), dtype=np.float64)
    s = np.exp(1j * 2.0 * np.pi * float(tone_cycles_per_sample) * n)
    x = a[:, None] * s[None, :]
    noise_pow = 10.0 ** (-float(snr_db) / 10.0)
    noise = np.sqrt(noise_pow / 2.0) * (
        rng.standard_normal(x.shape) + 1j * rng.standard_normal(x.shape)
    )
    return np.ascontiguousarray(x + noise, dtype=np.complex64)


def make_theta30_frame(
    geometry: ArrayGeometry,
    *,
    fc_hz: float = DEFAULT_FC_HZ,
    fs_hz: float = DEFAULT_FS_HZ,
    n_samp: int = DEFAULT_N_SAMP,
    snr_db: float = DEFAULT_SNR_DB,
    theta_deg: float = DEFAULT_THETA_DEG,
    seed: int = DEFAULT_SEED,
    frame_id: int = 1,
    timestamp_utc_ns: int = 0,
) -> IqFrame:
    rng = np.random.default_rng(int(seed))
    iq = uca_snapshot(
        geometry,
        theta_deg,
        fc_hz=fc_hz,
        n_samp=n_samp,
        snr_db=snr_db,
        rng=rng,
    )
    m = int(geometry.M)
    return IqFrame(
        schema_version=SCHEMA_VERSION,
        frame_id=int(frame_id),
        timestamp_utc_ns=int(timestamp_utc_ns),
        fc_hz=float(fc_hz),
        fs_hz=float(fs_hz),
        n_chan=m,
        n_samp=int(n_samp),
        dtype="complex64",
        layout="channel_first",
        endianness="little",
        channel_ids=list(range(m)),
        element_ids=[int(x) for x in geometry.element_ids],
        iq=iq,
    )


def write_npy_stem(frame: IqFrame, stem: str | Path) -> tuple[Path, Path]:
    stem_path = Path(stem)
    stem_path.parent.mkdir(parents=True, exist_ok=True)
    npy_path = stem_path.with_suffix(".npy")
    meta_path = Path(str(stem_path) + ".meta.json")
    np.save(npy_path, np.ascontiguousarray(frame.iq, dtype=np.complex64))
    meta_path.write_text(
        json.dumps(frame.meta_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return npy_path, meta_path


def default_sim_config(repo_root: Path) -> Path:
    return repo_root / "configs" / "array_uca_m4_sim.yaml"


def default_golden_stem(repo_root: Path) -> Path:
    return repo_root / "tests" / "golden" / "theta30_m4"


def generate_theta30_m4(
    repo_root: str | Path,
    *,
    config_path: str | Path | None = None,
    stem: str | Path | None = None,
) -> tuple[Path, Path]:
    root = Path(repo_root)
    cfg = Path(config_path) if config_path is not None else default_sim_config(root)
    out = Path(stem) if stem is not None else default_golden_stem(root)
    geometry = load_array_geometry(cfg)
    frame = make_theta30_frame(geometry)
    return write_npy_stem(frame, out)
