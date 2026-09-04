"""MUSIC direction finding.

Consumes DetectionEvent (and referenced IQ), produces AoAResult.
Array size M is variable; default M=4.
"""

from aoa.constants import C_MPS, DEFAULT_M, SCHEMA_VERSION
from aoa.errors import MissingArrayRadiusError
from aoa.estimator import MusicEstimator
from aoa.geometry import (
    ArrayGeometry,
    CalibFile,
    load_array_geometry,
    load_calib_file,
    steering_matrix,
)
from aoa.types import (
    AoAOutput,
    AoAResult,
    DetectionEvent,
    GeoFix,
    IqFrame,
    invalid_geo_fix,
)

__all__ = [
    "C_MPS",
    "DEFAULT_M",
    "SCHEMA_VERSION",
    "ArrayGeometry",
    "AoAOutput",
    "AoAResult",
    "CalibFile",
    "DetectionEvent",
    "GeoFix",
    "IqFrame",
    "MissingArrayRadiusError",
    "MusicEstimator",
    "invalid_geo_fix",
    "load_array_geometry",
    "load_calib_file",
    "steering_matrix",
]
