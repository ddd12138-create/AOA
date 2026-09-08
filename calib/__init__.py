"""Channel amplitude/phase calibration.

Produces CalibFile YAML for ArrayGeometry.calib_path.
identity.yaml stays the uncalibrated placeholder; this package writes
status=calibrated files only.
"""

from aoa.geometry import CalibFile, load_calib_file

from calib.cli import main
from calib.errors import CalibError, MissingArrayRadiusError, NoBurstError
from calib.estimate import calibrate_known_source, calibrate_replay, relative_gain_phase
from calib.io import IDENTITY_RELPATH, dump_calib_yaml, write_calib_file

__all__ = [
    "IDENTITY_RELPATH",
    "CalibError",
    "CalibFile",
    "MissingArrayRadiusError",
    "NoBurstError",
    "calibrate_known_source",
    "calibrate_replay",
    "dump_calib_yaml",
    "load_calib_file",
    "main",
    "relative_gain_phase",
    "write_calib_file",
]
