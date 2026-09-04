"""MUSIC spectrum and peak picking. No Qt, no UHD."""

from __future__ import annotations

import numpy as np

from aoa.constants import GRID_START_DEG, GRID_STEP_DEG, GRID_STOP_DEG, K_MAX_M4
from aoa.types import MusicPeak, MusicSpectrumSummary


def sample_covariance(iq: np.ndarray) -> np.ndarray:
    x = np.asarray(iq, dtype=np.complex128)
    if x.ndim != 2:
        raise ValueError("iq must have shape (M, N)")
    _m, n = x.shape
    if n < 1:
        raise ValueError("need at least one snapshot")
    rxx = (x @ x.conj().T) / float(n)
    return 0.5 * (rxx + rxx.conj().T)


def eig_sorted(rxx: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    eigvals, eigvecs = np.linalg.eigh(rxx)
    order = np.argsort(eigvals.real)[::-1]
    return eigvals.real[order], eigvecs[:, order]


def mdl_k(eigvals: np.ndarray, n_snap: int, k_max: int) -> int:
    """MDL source count in 0..k_max. Caller may clamp to >= 1 after a detection."""
    lam = np.maximum(np.asarray(eigvals, dtype=np.float64).real, 1e-30)
    m = lam.size
    k_max = int(max(0, min(k_max, m - 1)))
    best_k = 0
    best = np.inf
    log_n = np.log(max(int(n_snap), 2))
    for k in range(0, k_max + 1):
        noise = lam[k:]
        n_noise = noise.size
        arith = float(np.mean(noise))
        geom = float(np.exp(np.mean(np.log(noise))))
        mdl = n_snap * n_noise * np.log(arith / geom) + 0.5 * k * (2 * m - k) * log_n
        if mdl < best:
            best = mdl
            best_k = k
    return int(best_k)


def k_cap(m: int) -> int:
    if m <= 4:
        return min(m - 1, K_MAX_M4)
    return max(1, m - 1)


def estimate_k(eigvals: np.ndarray, n_snap: int, m: int, *, detected: bool = True) -> int:
    k = mdl_k(eigvals, n_snap, k_cap(m))
    if detected:
        k = max(k, 1)
    return int(min(k, k_cap(m)))


def music_power(steering: np.ndarray, noise_subspace: np.ndarray) -> np.ndarray:
    """P(θ) = 1 / ||E_n^H a(θ)||^2 for each column of steering (M, T)."""
    en = np.asarray(noise_subspace, dtype=np.complex128)
    a = np.asarray(steering, dtype=np.complex128)
    proj = en.conj().T @ a
    denom = np.sum(np.abs(proj) ** 2, axis=0)
    return 1.0 / np.maximum(denom, 1e-30)


def azimuth_grid_deg(
    start: float = GRID_START_DEG,
    stop: float = GRID_STOP_DEG,
    step: float = GRID_STEP_DEG,
) -> np.ndarray:
    if step <= 0:
        raise ValueError("grid step must be positive")
    n = int(np.round((stop - start) / step))
    return start + step * np.arange(n, dtype=np.float64)


def _wrap_index(i: int, n: int) -> int:
    return int(i) % n


def local_maxima_circular(power: np.ndarray) -> list[int]:
    p = np.asarray(power, dtype=np.float64)
    n = p.size
    peaks: list[int] = []
    for i in range(n):
        left = p[_wrap_index(i - 1, n)]
        right = p[_wrap_index(i + 1, n)]
        if p[i] > left and p[i] >= right:
            peaks.append(i)
    return peaks


def interpolate_peak_deg(thetas: np.ndarray, power: np.ndarray, index: int) -> float:
    """Parabolic interpolation on a circular dB spectrum; result in [0, 360)."""
    n = thetas.size
    step = float((thetas[1] - thetas[0]) if n > 1 else GRID_STEP_DEG)
    p_db = 10.0 * np.log10(np.maximum(power, 1e-30))
    y0 = p_db[_wrap_index(index - 1, n)]
    y1 = p_db[index]
    y2 = p_db[_wrap_index(index + 1, n)]
    denom = y0 - 2.0 * y1 + y2
    if abs(denom) < 1e-12:
        delta = 0.0
    else:
        delta = 0.5 * (y0 - y2) / denom
        delta = float(np.clip(delta, -1.0, 1.0))
    return float((thetas[index] + delta * step) % 360.0)


def pick_peaks(
    thetas: np.ndarray,
    power: np.ndarray,
    *,
    max_peaks: int = 8,
) -> list[MusicPeak]:
    p = np.asarray(power, dtype=np.float64)
    p_db = 10.0 * np.log10(np.maximum(p, 1e-30))
    idxs = local_maxima_circular(p)
    ranked = sorted(idxs, key=lambda i: float(p[i]), reverse=True)[:max_peaks]
    peaks: list[MusicPeak] = []
    for i in ranked:
        theta = interpolate_peak_deg(thetas, p, i)
        peaks.append(MusicPeak(theta_deg=theta, p_db=float(p_db[i])))
    peaks.sort(key=lambda pk: pk.p_db, reverse=True)
    return peaks


def spectrum_summary(
    thetas: np.ndarray,
    power: np.ndarray,
    *,
    grid_start_deg: float = GRID_START_DEG,
    grid_stop_deg: float = GRID_STOP_DEG,
    grid_step_deg: float = GRID_STEP_DEG,
) -> MusicSpectrumSummary:
    peaks = pick_peaks(thetas, power)
    return MusicSpectrumSummary(
        grid_start_deg=float(grid_start_deg),
        grid_stop_deg=float(grid_stop_deg),
        grid_step_deg=float(grid_step_deg),
        n_peaks=len(peaks),
        peaks=peaks,
    )


def confidence_from_spectrum(power: np.ndarray) -> float:
    p = np.asarray(power, dtype=np.float64)
    p_db = 10.0 * np.log10(np.maximum(p, 1e-30))
    contrast = float(np.max(p_db) - np.median(p_db))
    return float(np.clip(contrast / 40.0, 0.0, 1.0))
