"""Synthetic IQ with a known arrival angle. Builds replay goldens (e.g. theta=30 deg)."""

from sim.snapshot import generate_theta30_m4, make_theta30_frame, uca_snapshot, write_npy_stem

__all__ = [
    "generate_theta30_m4",
    "make_theta30_frame",
    "uca_snapshot",
    "write_npy_stem",
]
