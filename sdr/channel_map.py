"""ChannelMap loader and live-readiness checks (docs/interfaces.md)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from sdr.errors import LiveRejected, SdrError

ALLOWED_USRP_CHAN = ("A:0", "A:1", "B:0", "B:1")
LIVE_M = 4


@dataclass(frozen=True)
class ChannelMapping:
    channel_index: int
    element_id: int
    usrp_chan: str
    twinrx_slot: str
    twinrx_rx: int


@dataclass(frozen=True)
class ChannelMap:
    schema_version: int
    M: int
    lo_share: bool
    replay_only: bool
    device_args: str
    usrp_serial: str | None
    mapping: tuple[ChannelMapping, ...]

    def ordered(self) -> tuple[ChannelMapping, ...]:
        return tuple(sorted(self.mapping, key=lambda m: m.channel_index))

    def channel_ids(self) -> list[int]:
        return [m.channel_index for m in self.ordered()]

    def element_ids(self) -> list[int]:
        return [m.element_id for m in self.ordered()]

    def rx_subdev_spec(self) -> str:
        """UHD RX subdev spec in IqFrame / a(θ) row order."""
        return " ".join(m.usrp_chan for m in self.ordered())

    def device_args_resolved(self) -> str:
        parts: list[str] = []
        if self.device_args:
            parts.append(str(self.device_args).strip())
        if self.usrp_serial:
            parts.append(f"serial={self.usrp_serial}")
        return ",".join(p for p in parts if p)


def load_channel_map(path: str | Path) -> ChannelMap:
    p = Path(path)
    if not p.is_file():
        raise SdrError(f"channel map not found: {p}")
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SdrError("channel_map.yaml must be a mapping")
    return channel_map_from_dict(raw)


def channel_map_from_dict(raw: dict[str, Any]) -> ChannelMap:
    mapping_raw = raw.get("mapping")
    if not isinstance(mapping_raw, list) or not mapping_raw:
        raise SdrError("channel_map.mapping must be a non-empty list")
    mapping = tuple(
        ChannelMapping(
            channel_index=int(row["channel_index"]),
            element_id=int(row["element_id"]),
            usrp_chan=str(row["usrp_chan"]),
            twinrx_slot=str(row["twinrx_slot"]),
            twinrx_rx=int(row["twinrx_rx"]),
        )
        for row in mapping_raw
    )
    serial = raw.get("usrp_serial", None)
    if serial is not None:
        serial = str(serial)
    return ChannelMap(
        schema_version=int(raw.get("schema_version", 0)),
        M=int(raw["M"]),
        lo_share=bool(raw.get("lo_share", False)),
        replay_only=bool(raw.get("replay_only", False)),
        device_args=str(raw.get("device_args") or ""),
        usrp_serial=serial,
        mapping=mapping,
    )


def assert_live_allowed(channel_map: ChannelMap) -> None:
    """Refuse --live unless LO share is asserted and the map is one X310 / 4 ch.

    Does not import UHD.
    """
    if channel_map.schema_version != 1:
        raise LiveRejected("live refused: channel_map.schema_version must be 1")
    if channel_map.lo_share is not True:
        raise LiveRejected(
            "live refused: lo_share must be true (TwinRX intra- and inter-board LO share)"
        )
    if channel_map.M != LIVE_M:
        raise LiveRejected(
            f"live refused: one X310 + 2xTwinRX is M={LIVE_M}; got M={channel_map.M}"
        )
    if len(channel_map.mapping) != LIVE_M:
        raise LiveRejected(
            f"live refused: mapping length must be {LIVE_M}, got {len(channel_map.mapping)}"
        )

    ordered = channel_map.ordered()
    indices = [m.channel_index for m in ordered]
    if indices != list(range(LIVE_M)):
        raise LiveRejected(
            f"live refused: channel_index must be 0..{LIVE_M - 1} uniquely, got {indices}"
        )
    for row in ordered:
        if row.usrp_chan not in ALLOWED_USRP_CHAN:
            raise LiveRejected(
                f"live refused: usrp_chan {row.usrp_chan!r} is not a TwinRX port "
                f"on one X310 ({', '.join(ALLOWED_USRP_CHAN)})"
            )
        if row.twinrx_slot not in ("A", "B"):
            raise LiveRejected(f"live refused: twinrx_slot must be A or B, got {row.twinrx_slot!r}")
        if row.twinrx_rx not in (0, 1):
            raise LiveRejected(f"live refused: twinrx_rx must be 0 or 1, got {row.twinrx_rx}")
