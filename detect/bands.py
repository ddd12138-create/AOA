"""Map IqFrame.fc_hz onto configs/bands.yaml ids (900M / 2.4G / 5.8G)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from detect.errors import DetectError
from detect.types import BAND_IDS

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BANDS_PATH = REPO_ROOT / "configs" / "bands.yaml"

# Half-width around each yaml centre so 0.84 GHz still counts as 900M
# and nearby ISM tunes still map. Not a protocol channel plan.
_DEFAULT_HALF_WIDTH_HZ = {
    "900M": 100e6,
    "2.4G": 120e6,
    "5.8G": 150e6,
}

_BUILTIN = (
    ("900M", 900_000_000.0),
    ("2.4G", 2_400_000_000.0),
    ("5.8G", 5_800_000_000.0),
)


@dataclass(frozen=True)
class BandSpec:
    band_id: str
    fc_hz: float
    half_width_hz: float

    @property
    def lo_hz(self) -> float:
        return float(self.fc_hz) - float(self.half_width_hz)

    @property
    def hi_hz(self) -> float:
        return float(self.fc_hz) + float(self.half_width_hz)

    def contains(self, fc_hz: float) -> bool:
        return self.lo_hz <= float(fc_hz) <= self.hi_hz


def _half_width(band_id: str) -> float:
    return float(_DEFAULT_HALF_WIDTH_HZ.get(band_id, 50e6))


def builtin_bands() -> tuple[BandSpec, ...]:
    return tuple(
        BandSpec(band_id=name, fc_hz=fc, half_width_hz=_half_width(name))
        for name, fc in _BUILTIN
    )


def load_bands(path: str | Path | None = None) -> tuple[BandSpec, ...]:
    """Load band centres from yaml. Missing file falls back to the three ISM ids."""
    p = Path(path) if path is not None else DEFAULT_BANDS_PATH
    if not p.is_file():
        return builtin_bands()
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise DetectError(f"bands.yaml must be a mapping: {p}")
    rows = raw.get("bands")
    if not isinstance(rows, list) or not rows:
        raise DetectError(f"bands.yaml missing bands list: {p}")
    specs: list[BandSpec] = []
    for row in rows:
        if not isinstance(row, dict):
            raise DetectError("each bands[] entry must be a mapping")
        band_id = str(row["id"])
        if band_id not in BAND_IDS:
            raise DetectError(f"unknown band id {band_id!r}; expected {BAND_IDS}")
        specs.append(
            BandSpec(
                band_id=band_id,
                fc_hz=float(row["fc_hz"]),
                half_width_hz=_half_width(band_id),
            )
        )
    have = {s.band_id for s in specs}
    missing = [b for b in BAND_IDS if b not in have]
    if missing:
        raise DetectError(f"bands.yaml must cover {BAND_IDS}, missing {missing}")
    return tuple(specs)


def classify_band(fc_hz: float, bands: tuple[BandSpec, ...] | None = None) -> str | None:
    """Return band id if fc_hz sits in a configured window; else None (do not emit)."""
    specs = bands if bands is not None else load_bands()
    hits = [s for s in specs if s.contains(fc_hz)]
    if not hits:
        return None
    return min(hits, key=lambda s: abs(s.fc_hz - float(fc_hz))).band_id
