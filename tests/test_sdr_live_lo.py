"""TwinRX LO share helpers in sdr.live (no UHD, no radio)."""

from __future__ import annotations

import subprocess
import sys
from types import SimpleNamespace

import pytest

from sdr.channel_map import channel_map_from_dict
from sdr.errors import SdrError
from sdr.live import (
    LO_STAGE,
    apply_twinrx_lo_share,
    describe_twinrx_lo,
    lo_locked_from_sensor,
    twinrx_lo_plan,
    twinrx_lo_unlock_message,
    wait_twinrx_lo_locked,
)


def _map() -> object:
    return channel_map_from_dict(
        {
            "schema_version": 1,
            "M": 4,
            "lo_share": True,
            "replay_only": False,
            "device_args": "resource=RIO0",
            "usrp_serial": "3229FCE",
            "mapping": [
                {
                    "channel_index": 0,
                    "element_id": 1,
                    "usrp_chan": "A:0",
                    "twinrx_slot": "A",
                    "twinrx_rx": 0,
                },
                {
                    "channel_index": 1,
                    "element_id": 3,
                    "usrp_chan": "A:1",
                    "twinrx_slot": "A",
                    "twinrx_rx": 1,
                },
                {
                    "channel_index": 2,
                    "element_id": 5,
                    "usrp_chan": "B:0",
                    "twinrx_slot": "B",
                    "twinrx_rx": 0,
                },
                {
                    "channel_index": 3,
                    "element_id": 7,
                    "usrp_chan": "B:1",
                    "twinrx_slot": "B",
                    "twinrx_rx": 1,
                },
            ],
        }
    )


class _Sensor:
    def __init__(self, locked: bool) -> None:
        self._locked = locked

    def to_bool(self) -> bool:
        return self._locked


class FakeUsrp:
    def __init__(self, locked: list[bool] | None = None) -> None:
        self.lo_source = ["internal"] * 4
        self.lo_export = [False] * 4
        self.locked = locked if locked is not None else [True, True, True, True]
        self.calls: list[tuple] = []

    def set_rx_lo_source(self, src: str, name: str, chan: int) -> None:
        if name != "all":
            raise RuntimeError(f"RFNoC has no {name!r} path")
        self.calls.append(("source", src, name, chan))
        self.lo_source[chan] = src

    def set_rx_lo_export_enabled(self, enabled: bool, name: str, chan: int) -> None:
        if name != "all":
            raise RuntimeError(f"RFNoC has no {name!r} path")
        self.calls.append(("export", bool(enabled), name, chan))
        self.lo_export[chan] = bool(enabled)

    def get_rx_lo_source(self, name: str, chan: int) -> str:
        if name != "all":
            raise RuntimeError(f"RFNoC has no {name!r} path")
        return self.lo_source[chan]

    def get_rx_lo_export_enabled(self, name: str, chan: int) -> bool:
        if name != "all":
            raise RuntimeError(f"RFNoC has no {name!r} path")
        return self.lo_export[chan]

    def get_rx_sensor_names(self, chan: int) -> list[str]:
        return ["lo_locked"]

    def get_rx_sensor(self, name: str, chan: int) -> _Sensor:
        if name != "lo_locked":
            raise RuntimeError(name)
        return _Sensor(self.locked[chan])


def test_import_live_does_not_import_uhd():
    code = (
        "import sys\n"
        "from sdr.live import twinrx_lo_plan, LO_STAGE\n"
        "assert LO_STAGE == 'all'\n"
        "assert 'uhd' not in sys.modules\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


def test_lo_plan_is_internal_export_companion_external_companion():
    plan = twinrx_lo_plan(_map())
    by_chan = {chan: (slot, source, export) for chan, slot, source, export in plan}
    assert by_chan[0] == ("A", "internal", True)
    assert by_chan[1] == ("A", "companion", False)
    assert by_chan[2] == ("B", "external", False)
    assert by_chan[3] == ("B", "companion", False)
    assert plan[0][3] is True
    assert LO_STAGE == "all"


def test_apply_uses_all_stage_and_expected_sources():
    usrp = FakeUsrp()
    apply_twinrx_lo_share(usrp, _map())
    sources = [c for c in usrp.calls if c[0] == "source"]
    exports = [c for c in usrp.calls if c[0] == "export"]
    assert all(c[2] == "all" for c in sources + exports)
    assert not any("LO1" in str(c) or "LO2" in str(c) for c in usrp.calls)
    by_chan = {c[3]: c[1] for c in sources}
    assert by_chan == {0: "internal", 1: "companion", 2: "external", 3: "companion"}
    assert usrp.lo_export == [True, False, False, False]


def test_slot_b_unlock_mentions_mmcx_and_refuses():
    usrp = FakeUsrp(locked=[True, True, False, False])
    apply_twinrx_lo_share(usrp, _map())
    with pytest.raises(SdrError, match="MMCX") as exc:
        wait_twinrx_lo_locked(usrp, _map(), timeout_s=0.0, sleep_s=0.0)
    assert "independent LOs" in str(exc.value)
    assert "Slot B" in str(exc.value)


def test_slot_a_unlock_does_not_blame_mmcx():
    plan = twinrx_lo_plan(_map())
    msg = twinrx_lo_unlock_message(plan, [False, False, True, True])
    assert "Slot A" in msg
    assert "MMCX" not in msg


def test_wait_locked_ok():
    usrp = FakeUsrp()
    apply_twinrx_lo_share(usrp, _map())
    locked = wait_twinrx_lo_locked(usrp, _map(), timeout_s=0.0, sleep_s=0.0)
    assert locked == [True, True, True, True]
    line = describe_twinrx_lo(twinrx_lo_plan(_map()), locked)
    assert "ch0 A internal export" in line
    assert "ch2 B external" in line
    assert "lo_locked=true,true,true,true" in line


def test_lo_locked_from_sensor_variants():
    assert lo_locked_from_sensor(_Sensor(True)) is True
    assert lo_locked_from_sensor(_Sensor(False)) is False
    assert lo_locked_from_sensor(SimpleNamespace(value="LO: locked")) is True
    assert lo_locked_from_sensor(SimpleNamespace(value="unlocked")) is False
    assert lo_locked_from_sensor(None) is False


def test_is_rx_overflow_matches_uhd_enum_string():
    from sdr.errors import RxOverflow
    from sdr.live import is_rx_overflow

    assert is_rx_overflow("rx_metadata_error_code.overflow") is True
    assert is_rx_overflow("OVERFLOW") is True
    assert is_rx_overflow("none") is False
    assert is_rx_overflow(None) is False
    assert issubclass(RxOverflow, Exception)
