"""Calibration errors. Missing R_m must abort; never invent a radius."""

from aoa.errors import MissingArrayRadiusError

__all__ = ["CalibError", "NoBurstError", "MissingArrayRadiusError"]


class CalibError(ValueError):
    """Invalid replay, geometry, or output path. Not used for identity placeholder."""


class NoBurstError(CalibError):
    """detect produced no DetectionEvent; known-source calib needs a burst."""
