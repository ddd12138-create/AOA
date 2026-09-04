"""ArrayGeometry / CalibFile loaders and UCA steering vectors a(θ)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import yaml

from aoa.constants import C_MPS, DEFAULT_M, SCHEMA_VERSION
from aoa.errors import MissingArrayRadiusError

HFSS_HINT = (
    "Do not substitute HFSS '半径 xx mm' from 阵列天线/优化结果/ for ArrayGeometry.R_m."
)


@dataclass(frozen=True)
class ArrayGeometry:
    schema_version: int
    array_type: str
    M: int
    element_ids: tuple[int, ...]
    R_m: float | None
    phi_deg: tuple[float, ...]
    north_offset_deg: float
    calib_path: str

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        if self.array_type != "UCA":
            raise ValueError('array_type must be "UCA"')
        if self.M < 1:
            raise ValueError("M must be >= 1")
        if len(self.element_ids) != self.M or len(self.phi_deg) != self.M:
            raise ValueError("element_ids and phi_deg length must equal M")


@dataclass(frozen=True)
class CalibFile:
    schema_version: int
    M: int
    channel_ids: tuple[int, ...]
    gain_lin: tuple[float, ...]
    phase_rad: tuple[float, ...]
    status: str
    fc_hz: float | None

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        if self.status not in ("identity", "calibrated"):
            raise ValueError('status must be "identity" or "calibrated"')
        if not (self.M == len(self.channel_ids) == len(self.gain_lin) == len(self.phase_rad)):
            raise ValueError("CalibFile vector lengths must equal M")

    @property
    def uncalibrated(self) -> bool:
        return self.status == "identity"

    def weights(self) -> np.ndarray:
        gain = np.asarray(self.gain_lin, dtype=np.float64)
        phase = np.asarray(self.phase_rad, dtype=np.float64)
        return (gain * np.exp(1j * phase)).astype(np.complex128)


def _require_keys(data: dict[str, Any], keys: Sequence[str], what: str) -> None:
    missing = [k for k in keys if k not in data]
    if missing:
        raise KeyError(f"{what} missing keys: {missing}")


def load_array_geometry(path: str | Path) -> ArrayGeometry:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"ArrayGeometry YAML must be a mapping: {path}")
    _require_keys(
        raw,
        (
            "schema_version",
            "array_type",
            "M",
            "element_ids",
            "R_m",
            "phi_deg",
            "north_offset_deg",
            "calib_path",
        ),
        "ArrayGeometry",
    )
    r_raw = raw["R_m"]
    r_m: float | None
    if r_raw is None:
        r_m = None
    else:
        r_m = float(r_raw)
    return ArrayGeometry(
        schema_version=int(raw["schema_version"]),
        array_type=str(raw["array_type"]),
        M=int(raw["M"]),
        element_ids=tuple(int(x) for x in raw["element_ids"]),
        R_m=r_m,
        phi_deg=tuple(float(x) for x in raw["phi_deg"]),
        north_offset_deg=float(raw["north_offset_deg"]),
        calib_path=str(raw["calib_path"]),
    )


def load_calib_file(path: str | Path) -> CalibFile:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"CalibFile YAML must be a mapping: {path}")
    _require_keys(
        raw,
        (
            "schema_version",
            "M",
            "channel_ids",
            "gain_lin",
            "phase_rad",
            "status",
            "fc_hz",
        ),
        "CalibFile",
    )
    fc = raw["fc_hz"]
    return CalibFile(
        schema_version=int(raw["schema_version"]),
        M=int(raw["M"]),
        channel_ids=tuple(int(x) for x in raw["channel_ids"]),
        gain_lin=tuple(float(x) for x in raw["gain_lin"]),
        phase_rad=tuple(float(x) for x in raw["phase_rad"]),
        status=str(raw["status"]),
        fc_hz=None if fc is None else float(fc),
    )


def resolve_calib_path(geometry: ArrayGeometry, repo_root: str | Path) -> Path:
    return Path(repo_root) / geometry.calib_path


def require_radius_m(geometry: ArrayGeometry) -> float:
    """Return R_m in metres, or refuse. Never guess a jig / HFSS radius."""
    r_m = geometry.R_m
    if r_m is None:
        raise MissingArrayRadiusError(
            "ArrayGeometry.R_m is null; refusing azimuth. Measure the fixture "
            "centre-to-element radius in metres and set R_m. " + HFSS_HINT
        )
    if not np.isfinite(r_m) or r_m <= 0.0:
        raise MissingArrayRadiusError(
            f"ArrayGeometry.R_m={r_m!r} is not a positive radius in metres. "
            + HFSS_HINT
        )
    return float(r_m)


def wavelength_m(fc_hz: float, c_mps: float = C_MPS) -> float:
    if not np.isfinite(fc_hz) or fc_hz <= 0.0:
        raise ValueError("fc_hz must be a positive finite frequency in Hz")
    return float(c_mps / fc_hz)


def steering_matrix(
    theta_deg: np.ndarray | Sequence[float],
    geometry: ArrayGeometry,
    fc_hz: float,
    calib: CalibFile | None = None,
    *,
    c_mps: float = C_MPS,
) -> np.ndarray:
    """UCA manifold A, shape (M, n_theta).

    a(θ)_m = exp(j 2π R/λ cos(θ − φ_m)), then row-multiplied by calib weights.
    θ, φ in the array frame, CCW from array 0° (interfaces.md formula (2)).
    """
    r_m = require_radius_m(geometry)
    lam = wavelength_m(fc_hz, c_mps=c_mps)
    theta = np.deg2rad(np.asarray(theta_deg, dtype=np.float64).reshape(-1))
    phi = np.deg2rad(np.asarray(geometry.phi_deg, dtype=np.float64))
    # (M, T)
    phase = 2.0 * np.pi * (r_m / lam) * np.cos(theta[None, :] - phi[:, None])
    a = np.exp(1j * phase)
    if calib is not None:
        if calib.M != geometry.M:
            raise ValueError("CalibFile.M must match ArrayGeometry.M")
        a = a * calib.weights()[:, None]
    return a.astype(np.complex128)


def default_phi_deg(m: int = DEFAULT_M) -> tuple[float, ...]:
    if m == 4:
        return (0.0, 90.0, 180.0, 270.0)
    step = 360.0 / m
    return tuple(i * step for i in range(m))
