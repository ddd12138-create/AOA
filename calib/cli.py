"""CLI: python -m calib --replay STEM --theta-deg θ --array YAML --out YAML."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from calib.errors import CalibError, MissingArrayRadiusError
from calib.estimate import calibrate_replay
from calib.io import write_calib_file


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_existing(path: str | Path) -> Path:
    p = Path(path)
    if p.exists():
        return p
    alt = repo_root() / p
    if alt.exists():
        return alt
    raise CalibError(f"path not found: {path}")


def resolve_replay_stem(stem: str | Path) -> Path:
    p = Path(stem)
    candidates = [p, repo_root() / p]
    for base in candidates:
        npy = base.with_suffix(".npy")
        meta = Path(str(base) + ".meta.json")
        if npy.is_file() and meta.is_file():
            return base
        if base.suffix == ".npy" and base.is_file() and Path(str(base.with_suffix("")) + ".meta.json").is_file():
            return base.with_suffix("")
    raise CalibError(f"replay stem not found (need .npy + .meta.json): {stem}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="calib",
        description=(
            "Narrowband known-source channel amplitude/phase calibration. "
            "Writes a CalibFile YAML (status=calibrated). Does not touch identity.yaml."
        ),
    )
    parser.add_argument(
        "--replay",
        required=True,
        metavar="STEM",
        help="IqFrame stem (<stem>.npy + <stem>.meta.json); no X310",
    )
    parser.add_argument(
        "--theta-deg",
        required=True,
        type=float,
        help="known arrival angle in the array frame, degrees",
    )
    parser.add_argument(
        "--array",
        required=True,
        help="ArrayGeometry YAML (simulation: configs/array_uca_m4_sim.yaml)",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="output CalibFile YAML (must not be calib/identity.yaml)",
    )
    parser.add_argument(
        "--bands",
        default=None,
        help="optional configs/bands.yaml for detect",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        stem = resolve_replay_stem(args.replay)
        array_yaml = resolve_existing(args.array)
        bands = resolve_existing(args.bands) if args.bands else None
        out = Path(args.out)
        if not out.is_absolute():
            out = Path.cwd() / out
        calib = calibrate_replay(stem, float(args.theta_deg), array_yaml, bands_path=bands)
        written = write_calib_file(out, calib)
    except (CalibError, MissingArrayRadiusError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(written)
    return 0
