"""Spectrum scout and burst detector.

Consumes IqFrame, produces DetectionEvent.
Narrowband energy + burst segmentation on 900M / 2.4G / 5.8G.
No MUSIC, UHD, or protocol decode.
"""

from detect.bands import classify_band, load_bands
from detect.detector import EnergyBurstDetector, detect_frame
from detect.errors import DetectError
from detect.types import BAND_IDS, SCHEMA_VERSION, DetectionEvent, IqRef

__all__ = [
    "BAND_IDS",
    "SCHEMA_VERSION",
    "DetectError",
    "DetectionEvent",
    "EnergyBurstDetector",
    "IqRef",
    "classify_band",
    "detect_frame",
    "load_bands",
]
