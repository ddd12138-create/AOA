"""CLI for python -m sdr: --replay is always available; --live is optional."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sdr.channel_map import assert_live_allowed, load_channel_map
from sdr.errors import LiveRejected, ReplayError, SdrError
from sdr.replay import load_replay, save_replay

DEFAULT_FC_HZ = 2_400_000_000.0
DEFAULT_FS_HZ = 1_000_000.0
DEFAULT_GAIN_DB = 20.0
DEFAULT_N_SAMP = 4096
DEFAULT_CHANNEL_MAP = "configs/channel_map.yaml"


def add_source_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--replay",
        metavar="STEM",
        help="load <stem>.npy + <stem>.meta.json (no UHD required)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="one X310, 4 TwinRX channels; requires lo_share=true and UHD",
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_CHANNEL_MAP,
        help=f"channel_map.yaml (default {DEFAULT_CHANNEL_MAP})",
    )
    parser.add_argument("--fc-hz", type=float, default=DEFAULT_FC_HZ)
    parser.add_argument("--fs-hz", type=float, default=DEFAULT_FS_HZ)
    parser.add_argument("--gain-db", type=float, default=DEFAULT_GAIN_DB)
    parser.add_argument("--n-samp", type=int, default=DEFAULT_N_SAMP)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sdr",
        description="IqFrame acquisition and file replay (no Qt, no MUSIC).",
    )
    add_source_args(parser)
    parser.add_argument(
        "--save",
        metavar="STEM",
        help="with --live, write one frame as npy+meta.json",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if bool(args.replay) == bool(args.live):
        parser.error("specify exactly one of --replay STEM or --live")

    try:
        if args.replay:
            frame = load_replay(args.replay)
            sys.stdout.write(json.dumps(frame.to_header(), indent=2, ensure_ascii=False) + "\n")
            return 0

        cmap = load_channel_map(_resolve_config(args.config))
        assert_live_allowed(cmap)
        from sdr.live import LiveSource

        src = LiveSource(
            cmap,
            fc_hz=args.fc_hz,
            fs_hz=args.fs_hz,
            gain_db=args.gain_db,
            n_samp=args.n_samp,
        )
        try:
            src.start()
            frame = src.next_frame()
        finally:
            src.close()
        if args.save:
            save_replay(args.save, frame)
        sys.stdout.write(json.dumps(frame.to_header(), indent=2, ensure_ascii=False) + "\n")
        return 0
    except LiveRejected as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (ReplayError, SdrError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _resolve_config(path: str) -> Path:
    p = Path(path)
    if p.is_file():
        return p
    root = Path(__file__).resolve().parents[1]
    alt = root / path
    if alt.is_file():
        return alt
    return p
