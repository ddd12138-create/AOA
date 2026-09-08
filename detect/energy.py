"""Narrowband energy scan and time-domain burst segmentation.

No MUSIC, no UHD, no protocol decode. Operates on one already-tuned IqFrame.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

# Per-window peak/median (dB) after a Hann FFT. White noise max/median on
# a 64-pt FFT is typically ~8 dB; 11 dB plus a run-length gate keeps idle quiet.
WINDOW_SNR_DB = 11.0
# Full-frame Welch peak/median. Averaging knocks noise peaks down to a few dB.
FRAME_SNR_DB = 9.0
# Close a burst this far below the open threshold (hysteresis).
OFF_MARGIN_DB = 3.0
# If time-series dynamic range is below this, treat as continuous occupancy.
CONTINUOUS_DYN_DB = 6.0
# Merge gaps shorter than this many hops (packet chopping).
MERGE_HOPS = 2
HANG_HOPS = 2
DEFAULT_NPERSEG = 64
DEFAULT_HOP = 16
MIN_ACTIVE_WINDOWS = 3


@dataclass(frozen=True)
class OccupiedBand:
    """Baseband slice (Hz relative to IqFrame.fc_hz) that holds the energy."""

    offset_hz: float
    bw_hz: float
    snr_db: float
    bin_mask: np.ndarray
    df_hz: float


@dataclass(frozen=True)
class BurstSpan:
    start_samp: int
    end_samp: int


def _as_iq(iq: np.ndarray, n_chan: int, n_samp: int) -> np.ndarray:
    arr = np.asarray(iq)
    if arr.ndim != 2 or arr.shape != (n_chan, n_samp):
        raise ValueError(f"iq must have shape (n_chan, n_samp)=({n_chan}, {n_samp})")
    return np.ascontiguousarray(arr)


def _channel_mean(iq: np.ndarray) -> np.ndarray:
    """Power-average across channels (phase-insensitive)."""
    return np.mean(iq.real * iq.real + iq.imag * iq.imag, axis=0)


def _nperseg_for(n_samp: int) -> int:
    if n_samp < 16:
        return 0
    n = DEFAULT_NPERSEG
    while n > n_samp:
        n //= 2
    return max(n, 16) if n_samp >= 16 else 0


def _hop_for(nperseg: int) -> int:
    return max(1, min(DEFAULT_HOP, nperseg // 4 if nperseg >= 4 else 1))


def welch_psd(iq: np.ndarray, nperseg: int, hop: int) -> np.ndarray:
    """Mean periodogram across channels and overlapping Hann windows. Length nperseg."""
    window = np.hanning(nperseg).astype(np.float64)
    win_pow = float(np.dot(window, window)) + 1e-30
    _n_chan, n_samp = iq.shape
    acc: np.ndarray | None = None
    count = 0
    stop = n_samp - nperseg + 1
    if stop <= 0:
        spec = np.fft.fft(iq * window[:n_samp], n=nperseg, axis=1)
        return np.mean(np.abs(spec) ** 2, axis=0) / win_pow
    for start in range(0, stop, hop):
        seg = iq[:, start : start + nperseg].astype(np.complex128, copy=False)
        spec = np.fft.fft(seg * window, axis=1)
        p = np.mean(np.abs(spec) ** 2, axis=0)
        acc = p if acc is None else acc + p
        count += 1
    if acc is None:
        return np.full(nperseg, 1e-30, dtype=np.float64)
    return acc / (count * win_pow)


def _peak_vs_median_db(psd: np.ndarray) -> tuple[int, float]:
    med = float(np.median(psd))
    if not math.isfinite(med) or med <= 0.0:
        med = 1e-30
    peak_bin = int(np.argmax(psd))
    peak = float(psd[peak_bin])
    return peak_bin, 10.0 * math.log10(max(peak, 1e-30) / med)


def occupied_from_psd(psd: np.ndarray, fs_hz: float, *, floor_db: float = 3.0) -> OccupiedBand:
    nfft = int(psd.size)
    df = float(fs_hz) / float(nfft)
    peak_bin, snr_db = _peak_vs_median_db(psd)
    med = float(np.median(psd))
    floor = med * (10.0 ** (floor_db / 10.0))
    mask = np.zeros(nfft, dtype=bool)
    # Grow a contiguous (circular) island around the peak.
    mask[peak_bin] = True
    for step in (1, -1):
        idx = peak_bin
        for _ in range(nfft // 2):
            idx = (idx + step) % nfft
            if psd[idx] < floor:
                break
            mask[idx] = True
    n_bins = max(int(np.count_nonzero(mask)), 1)
    freqs = np.fft.fftfreq(nfft, d=1.0 / float(fs_hz))
    offset = float(freqs[peak_bin])
    return OccupiedBand(
        offset_hz=offset,
        bw_hz=float(n_bins) * df,
        snr_db=float(snr_db),
        bin_mask=mask,
        df_hz=df,
    )


def stft_band_and_median(
    iq: np.ndarray, nperseg: int, hop: int, bin_mask: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (starts, band_power, median_bin_power) per hop."""
    window = np.hanning(nperseg).astype(np.float64)
    n_samp = int(iq.shape[1])
    starts: list[int] = []
    band: list[float] = []
    meds: list[float] = []
    stop = n_samp - nperseg + 1
    if stop <= 0:
        return np.zeros(0, dtype=np.int64), np.zeros(0), np.zeros(0)
    for start in range(0, stop, hop):
        seg = iq[:, start : start + nperseg].astype(np.complex128, copy=False)
        spec = np.fft.fft(seg * window, axis=1)
        p = np.mean(np.abs(spec) ** 2, axis=0)
        starts.append(start)
        occupied = p[bin_mask]
        other = p[~bin_mask]
        band.append(float(np.mean(occupied)) if occupied.size else 0.0)
        meds.append(float(np.median(other)) if other.size else float(np.median(p)))
    return (
        np.asarray(starts, dtype=np.int64),
        np.asarray(band, dtype=np.float64),
        np.asarray(meds, dtype=np.float64),
    )


def _runs_from_active(active: np.ndarray, hang: int) -> list[tuple[int, int]]:
    """Inclusive window-index runs [i0, i1) with hang after drop."""
    runs: list[tuple[int, int]] = []
    n = int(active.size)
    i = 0
    while i < n:
        if not active[i]:
            i += 1
            continue
        i0 = i
        i += 1
        below = 0
        while i < n:
            if active[i]:
                below = 0
                i += 1
                continue
            below += 1
            if below > hang:
                i = i - below + 1
                break
            i += 1
        else:
            i = n
        runs.append((i0, i))
    return runs


def merge_runs(runs: list[tuple[int, int]], gap: int) -> list[tuple[int, int]]:
    if not runs:
        return []
    out = [runs[0]]
    for a, b in runs[1:]:
        pa, pb = out[-1]
        if a - pb <= gap:
            out[-1] = (pa, max(pb, b))
        else:
            out.append((a, b))
    return out


def segment_bursts(
    starts: np.ndarray,
    band_pow: np.ndarray,
    med_pow: np.ndarray,
    *,
    n_samp: int,
    nperseg: int,
    hop: int,
    on_db: float = WINDOW_SNR_DB,
    off_db: float | None = None,
    min_windows: int = MIN_ACTIVE_WINDOWS,
    hang: int = HANG_HOPS,
    merge_hops: int = MERGE_HOPS,
) -> list[BurstSpan]:
    if starts.size == 0:
        return []
    off = WINDOW_SNR_DB - OFF_MARGIN_DB if off_db is None else float(off_db)
    on_lin = 10.0 ** (on_db / 10.0)
    off_lin = 10.0 ** (off / 10.0)
    ratio = band_pow / np.maximum(med_pow, 1e-30)
    active = ratio >= on_lin
    # Hysteresis: once open, stay open down to off_lin.
    sticky = np.zeros(active.size, dtype=bool)
    open_ = False
    for i in range(active.size):
        if not open_:
            if active[i]:
                open_ = True
                sticky[i] = True
        else:
            if ratio[i] >= off_lin:
                sticky[i] = True
            else:
                open_ = False
    runs = merge_runs(_runs_from_active(sticky, hang=hang), gap=merge_hops)
    spans: list[BurstSpan] = []
    last_start = int(starts[-1])
    for i0, i1 in runs:
        if (i1 - i0) < int(min_windows):
            continue
        start = int(starts[i0])
        end = int(starts[i1 - 1]) + int(nperseg)
        if i0 == 0:
            start = 0
        if int(starts[i1 - 1]) >= last_start:
            end = int(n_samp)
        start = max(0, start)
        end = min(int(n_samp), max(start, end))
        spans.append(BurstSpan(start_samp=start, end_samp=end))
    return spans


def time_dynamic_range_db(power: np.ndarray) -> float:
    if power.size == 0:
        return 0.0
    hi = float(np.percentile(power, 90))
    lo = float(np.percentile(power, 10))
    return 10.0 * math.log10(max(hi, 1e-30) / max(lo, 1e-30))


def burst_snr_db(
    iq: np.ndarray,
    start: int,
    end: int,
    *,
    spectral_snr_db: float | None = None,
    nfft: int | None = None,
) -> float:
    """10 log10(P_on / P_off). All-on frames use peak/median minus Hann FFT gain."""
    inst = _channel_mean(iq)
    on = inst[start:end]
    off_parts = []
    if start > 0:
        off_parts.append(inst[:start])
    if end < inst.size:
        off_parts.append(inst[end:])
    off = np.concatenate(off_parts) if off_parts else np.zeros(0)
    p_on = float(np.mean(on)) if on.size else 0.0
    if p_on <= 0.0:
        return float("-inf")
    if off.size >= max(8, (end - start) // 8):
        p_off = float(np.mean(off))
        return 10.0 * math.log10(p_on / max(p_off, 1e-30))
    if spectral_snr_db is not None:
        snr = float(spectral_snr_db)
        if nfft is not None and nfft > 1:
            # Hann equivalent noise BW ~ 1.5 bins; undo FFT concentration.
            snr -= 10.0 * math.log10(float(nfft) / 1.5)
        return snr
    return 10.0 * math.log10(p_on / max(float(np.percentile(on, 10)), 1e-30))


def scan_frame(
    iq: np.ndarray,
    fs_hz: float,
    n_chan: int,
    n_samp: int,
    *,
    frame_snr_db: float = FRAME_SNR_DB,
    window_snr_db: float = WINDOW_SNR_DB,
) -> tuple[OccupiedBand | None, list[BurstSpan]]:
    """Return occupied baseband slice and burst spans, or (None, []) if idle."""
    x = _as_iq(iq, n_chan, n_samp)
    nperseg = _nperseg_for(n_samp)
    if nperseg == 0:
        return None, []
    hop = _hop_for(nperseg)
    psd = welch_psd(x, nperseg, hop)
    occ = occupied_from_psd(psd, fs_hz)
    starts, band_pow, med_pow = stft_band_and_median(x, nperseg, hop, occ.bin_mask)
    if starts.size == 0:
        return None, []

    inst = _channel_mean(x)
    win_pow = np.array(
        [float(np.mean(inst[s : s + nperseg])) for s in starts],
        dtype=np.float64,
    )
    dyn_db = time_dynamic_range_db(win_pow)
    on_lin = 10.0 ** (float(window_snr_db) / 10.0)
    hot = (band_pow / np.maximum(med_pow, 1e-30)) >= on_lin
    hot_frac = float(np.mean(hot)) if hot.size else 0.0
    strong_spectrum = occ.snr_db >= float(frame_snr_db)
    # Stationary noise also has low time dyn; require the same bins to stay hot.
    persistent = strong_spectrum and hot_frac >= 0.55

    if persistent and dyn_db < CONTINUOUS_DYN_DB:
        return occ, [BurstSpan(start_samp=0, end_samp=int(n_samp))]

    spans = segment_bursts(
        starts,
        band_pow,
        med_pow,
        n_samp=n_samp,
        nperseg=nperseg,
        hop=hop,
        on_db=window_snr_db,
    )
    if spans:
        return occ, spans
    if persistent:
        return occ, [BurstSpan(start_samp=0, end_samp=int(n_samp))]
    return None, []
