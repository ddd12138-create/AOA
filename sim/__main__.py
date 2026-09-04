"""Write tests/golden/theta30_m4.npy + .meta.json (simulation only)."""

from __future__ import annotations

import argparse
from pathlib import Path

from sim.snapshot import generate_theta30_m4


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate UCA M=4 theta=30° golden IQ")
    parser.add_argument(
        "--config",
        default=str(repo_root() / "configs" / "array_uca_m4_sim.yaml"),
        help="ArrayGeometry YAML with an explicit simulation R_m",
    )
    parser.add_argument(
        "--out",
        default=str(repo_root() / "tests" / "golden" / "theta30_m4"),
        help="output stem (writes .npy and .meta.json)",
    )
    args = parser.parse_args(argv)
    npy, meta = generate_theta30_m4(repo_root(), config_path=args.config, stem=args.out)
    print(npy)
    print(meta)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
