"""One X310 + two TwinRX (M=4) live capture. UHD is imported only when opening the radio."""

from __future__ import annotations

import sys
import threading
import time
from types import ModuleType

import numpy as np

from sdr.channel_map import ChannelMap, assert_live_allowed
from sdr.errors import SdrError
from sdr.iqframe import IqFrame, make_iq_frame

# This machine's RFNoC tree has no LO1/LO2 paths; TwinRX LO APIs must use "all".
LO_STAGE = "all"
LO_LOCK_TIMEOUT_S = 2.0
LO_LOCK_POLL_S = 0.05
TUNE_CMD_DELAY_S = 0.10

# Slot A RX0 is the shared synthesizer. Intra-board: companion. Inter-board: MMCX external.
_TWINRX_LO_BY_PORT: dict[tuple[str, int], tuple[str, bool]] = {
    ("A", 0): ("internal", True),
    ("A", 1): ("companion", False),
    ("B", 0): ("external", False),
    ("B", 1): ("companion", False),
}

_UHD: ModuleType | None = None


def _require_uhd() -> ModuleType:
    global _UHD
    if _UHD is not None:
        return _UHD
    try:
        import uhd as uhd_mod
    except ImportError as exc:
        raise SdrError(
            "live requires UHD Python bindings (Ettus installer or conda-forge::uhd); "
            "use --replay when no radio is installed"
        ) from exc
    _UHD = uhd_mod
    return uhd_mod


def _tune_request(uhd: ModuleType, fc_hz: float):
    types = getattr(uhd, "types", None)
    if types is not None and hasattr(types, "TuneRequest"):
        return types.TuneRequest(float(fc_hz))
    return float(fc_hz)


def _stream_mode(uhd: ModuleType, which: str):
    """UHD 4.9 Python uses start_cont/stop_cont; older bindings use *_continuous."""
    mode = getattr(uhd.types, "StreamMode", None)
    if mode is None:
        raise SdrError("UHD types.StreamMode is missing")
    names = {
        "start": ("start_continuous", "start_cont"),
        "stop": ("stop_continuous", "stop_cont"),
    }[which]
    for name in names:
        val = getattr(mode, name, None)
        if val is not None:
            return val
    raise SdrError(f"UHD StreamMode has none of {names}")


def twinrx_lo_plan(channel_map: ChannelMap) -> tuple[tuple[int, str, str, bool], ...]:
    """UHD chan, TwinRX slot, LO source, export_enabled. Master (export) first."""
    rows: list[tuple[int, str, str, bool]] = []
    for row in channel_map.ordered():
        key = (row.twinrx_slot, row.twinrx_rx)
        spec = _TWINRX_LO_BY_PORT.get(key)
        if spec is None:
            raise SdrError(
                f"TwinRX LO plan missing for slot {row.twinrx_slot} rx{row.twinrx_rx}"
            )
        source, export = spec
        rows.append((row.channel_index, row.twinrx_slot, source, export))
    rows.sort(key=lambda item: (0 if item[3] else 1, item[0]))
    return tuple(rows)


def lo_locked_from_sensor(val: object) -> bool:
    if val is None:
        return False
    to_bool = getattr(val, "to_bool", None)
    if callable(to_bool):
        try:
            return bool(to_bool())
        except Exception:
            pass
    if isinstance(val, bool):
        return val
    text = str(getattr(val, "value", val)).strip().lower()
    if text in {"true", "1", "locked", "yes"}:
        return True
    if text in {"false", "0", "unlocked", "no"}:
        return False
    if "unlocked" in text:
        return False
    if "locked" in text:
        return True
    return False


def twinrx_lo_unlock_message(
    plan: tuple[tuple[int, str, str, bool], ...],
    locked: list[bool],
) -> str:
    by_chan = {chan: (slot, source) for chan, slot, source, _export in plan}
    unlocked: list[str] = []
    slot_b = False
    for chan, ok in enumerate(locked):
        if ok:
            continue
        slot, source = by_chan.get(chan, ("?", "?"))
        unlocked.append(f"ch{chan}(slot {slot},{source})")
        if slot == "B":
            slot_b = True
    if not unlocked:
        return "TwinRX LO unlocked"
    msg = "TwinRX LO unlocked: " + ", ".join(unlocked) + "."
    if slot_b:
        msg += (
            " Slot B lost lock: board-to-board MMCX LO cables are probably not connected "
            "(J1/J2 LO2 and J3/J4 LO1). Refusing to continue with independent LOs."
        )
    else:
        msg += " Slot A internal synthesizer did not lock."
    return msg


def apply_twinrx_lo_share(usrp: object, channel_map: ChannelMap) -> tuple[tuple[int, str, str, bool], ...]:
    """Program TwinRX LO sources. Name is always 'all' (no LO1/LO2 RFNoC paths)."""
    plan = twinrx_lo_plan(channel_map)
    for chan, slot, source, export in plan:
        try:
            usrp.set_rx_lo_source(source, LO_STAGE, chan)
            usrp.set_rx_lo_export_enabled(bool(export), LO_STAGE, chan)
        except Exception as exc:
            raise SdrError(
                f"TwinRX ch{chan} (slot {slot}) set_rx_lo_source({source!r}, {LO_STAGE!r}) failed: {exc}"
            ) from exc
        _assert_lo_programmed(usrp, chan, slot, source, bool(export))
    return plan


def wait_twinrx_lo_locked(
    usrp: object,
    channel_map: ChannelMap,
    *,
    timeout_s: float = LO_LOCK_TIMEOUT_S,
    sleep_s: float = LO_LOCK_POLL_S,
) -> list[bool]:
    plan = twinrx_lo_plan(channel_map)
    n_chan = len(channel_map.ordered())
    deadline = time.monotonic() + max(0.0, float(timeout_s))
    locked = [False] * n_chan
    while True:
        locked = [_read_lo_locked(usrp, ch) for ch in range(n_chan)]
        if all(locked):
            return locked
        if time.monotonic() >= deadline:
            raise SdrError(twinrx_lo_unlock_message(plan, locked))
        time.sleep(sleep_s)


def describe_twinrx_lo(
    plan: tuple[tuple[int, str, str, bool], ...],
    locked: list[bool] | None = None,
) -> str:
    parts: list[str] = []
    for chan, slot, source, export in sorted(plan, key=lambda item: item[0]):
        extra = " export" if export else ""
        parts.append(f"ch{chan} {slot} {source}{extra}")
    line = "TwinRX LO share: " + ", ".join(parts)
    if locked is not None:
        line += "; lo_locked=" + ",".join("true" if x else "false" for x in locked)
    return line


def _assert_lo_programmed(
    usrp: object,
    chan: int,
    slot: str,
    source: str,
    export: bool,
) -> None:
    try:
        got_src = usrp.get_rx_lo_source(LO_STAGE, chan)
    except Exception as exc:
        raise SdrError(
            f"TwinRX ch{chan} (slot {slot}) get_rx_lo_source({LO_STAGE!r}) failed: {exc}"
        ) from exc
    if not _lo_source_matches(got_src, source):
        raise SdrError(
            f"TwinRX ch{chan} (slot {slot}) LO source is {got_src!r}, expected {source!r} "
            f"(stage {LO_STAGE!r})"
        )
    try:
        got_export = usrp.get_rx_lo_export_enabled(LO_STAGE, chan)
    except Exception as exc:
        raise SdrError(
            f"TwinRX ch{chan} (slot {slot}) get_rx_lo_export_enabled({LO_STAGE!r}) failed: {exc}"
        ) from exc
    if _flag_from_uhd(got_export) != bool(export):
        raise SdrError(
            f"TwinRX ch{chan} (slot {slot}) LO export is {got_export!r}, expected {export}"
        )


def _lo_source_matches(got: object, expected: str) -> bool:
    if isinstance(got, (list, tuple)):
        return bool(got) and all(str(x).strip().lower() == expected.lower() for x in got)
    return str(got).strip().lower() == expected.lower()


def _flag_from_uhd(val: object) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    text = str(val).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no", ""}:
        return False
    return bool(val)


def _read_lo_locked(usrp: object, chan: int) -> bool:
    try:
        names = [str(n) for n in usrp.get_rx_sensor_names(chan)]
    except Exception as exc:
        raise SdrError(f"TwinRX ch{chan} get_rx_sensor_names failed: {exc}") from exc
    if "lo_locked" not in names:
        raise SdrError(
            f"TwinRX ch{chan} has no lo_locked sensor (got {names!r}); cannot verify LO share"
        )
    try:
        val = usrp.get_rx_sensor("lo_locked", chan)
    except Exception as exc:
        raise SdrError(f"TwinRX ch{chan} lo_locked read failed: {exc}") from exc
    return lo_locked_from_sensor(val)


class LiveSource:
    """Blocking 4-channel receiver. Channel rows follow ChannelMap order."""

    def __init__(
        self,
        channel_map: ChannelMap,
        *,
        fc_hz: float,
        fs_hz: float,
        gain_db: float,
        n_samp: int,
    ) -> None:
        assert_live_allowed(channel_map)
        if n_samp < 1:
            raise SdrError("n_samp must be >= 1")
        self.channel_map = channel_map
        self.fc_hz = float(fc_hz)
        self.fs_hz = float(fs_hz)
        self.gain_db = float(gain_db)
        self.n_samp = int(n_samp)
        self.n_chan = channel_map.M
        self._frame_id = 0
        self._streaming = False
        self._io = threading.Lock()
        self._uhd = _require_uhd()
        self._usrp = None
        self._streamer = None
        self._md = None
        self._lo_plan: tuple[tuple[int, str, str, bool], ...] | None = None
        self._open_radio()

    def _open_radio(self) -> None:
        uhd = self._uhd
        args = self.channel_map.device_args_resolved()
        self._usrp = uhd.usrp.MultiUSRP(args)
        self._use_internal_reference()
        spec = self.channel_map.rx_subdev_spec()
        try:
            self._usrp.set_rx_subdev_spec(spec)
        except TypeError:
            spec_cls = getattr(uhd.usrp, "SubdevSpec", None)
            if spec_cls is None:
                raise
            self._usrp.set_rx_subdev_spec(spec_cls(spec))

        try:
            self._usrp.set_master_clock_rate(200e6)
        except Exception:
            pass
        # X310: one tick rate for the radio; per-channel set_rx_rate can warn tick=0.
        self._usrp.set_rx_rate(self.fs_hz)
        self._lo_plan = apply_twinrx_lo_share(self._usrp, self.channel_map)
        self._tune_rx_all()
        for ch in range(self.n_chan):
            self._usrp.set_rx_gain(self.gain_db, ch)
        locked = wait_twinrx_lo_locked(self._usrp, self.channel_map)
        sys.stderr.write(describe_twinrx_lo(self._lo_plan, locked) + "\n")

        st_args = uhd.usrp.StreamArgs("fc32", "sc16")
        st_args.channels = list(range(self.n_chan))
        self._streamer = self._usrp.get_rx_stream(st_args)
        self._md = uhd.types.RXMetadata()

    def _use_internal_reference(self) -> None:
        """Single X310: both TwinRX slots take the motherboard clock.

        An external GPSDO on REF IN/PPS is only for multi-radio sync or a
        better absolute frequency; it is not TwinRX RF LO sharing.
        """
        usrp = self._usrp
        uhd = self._uhd
        try:
            usrp.set_clock_source("internal")
        except Exception as exc:
            raise SdrError("failed to select internal motherboard clock: " + str(exc)) from exc
        try:
            usrp.set_time_source("internal")
        except Exception:
            pass
        usrp.set_time_now(uhd.types.TimeSpec(0.0))

    def _tune_rx_all(self) -> None:
        """Tune all TwinRX channels together so DDC/CORDIC stay aligned."""
        uhd = self._uhd
        usrp = self._usrp
        req = _tune_request(uhd, self.fc_hz)
        timed = False
        try:
            now = usrp.get_time_now().get_real_secs()
            usrp.set_command_time(uhd.types.TimeSpec(now + TUNE_CMD_DELAY_S))
            timed = True
        except Exception:
            timed = False
        for ch in range(self.n_chan):
            usrp.set_rx_freq(req, ch)
        if timed:
            time.sleep(TUNE_CMD_DELAY_S + 0.05)
            try:
                usrp.clear_command_time()
            except Exception:
                pass
        else:
            time.sleep(0.10)

    def tune(
        self,
        *,
        fc_hz: float | None = None,
        fs_hz: float | None = None,
        gain_db: float | None = None,
    ) -> None:
        with self._io:
            restart = self._streaming
            if restart:
                self._stop_unlocked()
            if fc_hz is not None:
                self.fc_hz = float(fc_hz)
            if fs_hz is not None:
                self.fs_hz = float(fs_hz)
            if gain_db is not None:
                self.gain_db = float(gain_db)
            if fs_hz is not None:
                self._usrp.set_rx_rate(self.fs_hz)
            if fc_hz is not None:
                self._tune_rx_all()
            if gain_db is not None:
                for ch in range(self.n_chan):
                    self._usrp.set_rx_gain(self.gain_db, ch)
            if fc_hz is not None:
                wait_twinrx_lo_locked(self._usrp, self.channel_map)
            if restart:
                self._start_unlocked()

    def start(self) -> None:
        with self._io:
            self._start_unlocked()

    def stop(self) -> None:
        with self._io:
            self._stop_unlocked()

    def _start_unlocked(self) -> None:
        if self._streaming:
            return
        uhd = self._uhd
        cmd = uhd.types.StreamCMD(_stream_mode(uhd, "start"))
        if self.n_chan > 1:
            # stream_now cannot time-align multiple channels on one streamer.
            cmd.stream_now = False
            now = self._usrp.get_time_now().get_real_secs()
            cmd.time_spec = uhd.types.TimeSpec(now + 0.15)
        else:
            cmd.stream_now = True
        self._streamer.issue_stream_cmd(cmd)
        self._streaming = True

    def _stop_unlocked(self) -> None:
        if not self._streaming:
            return
        uhd = self._uhd
        cmd = uhd.types.StreamCMD(_stream_mode(uhd, "stop"))
        self._streamer.issue_stream_cmd(cmd)
        self._streaming = False

    def close(self) -> None:
        with self._io:
            try:
                self._stop_unlocked()
            finally:
                self._streamer = None
                self._usrp = None

    def next_frame(self, timeout_s: float = 3.0) -> IqFrame:
        with self._io:
            if not self._streaming:
                raise SdrError("live stream is stopped; send start first")
            iq = self._recv_exact(self.n_samp, timeout_s=timeout_s)
            frame_id = self._frame_id
            self._frame_id += 1
            return make_iq_frame(
                frame_id=frame_id,
                timestamp_utc_ns=time.time_ns(),
                fc_hz=self.fc_hz,
                fs_hz=self.fs_hz,
                channel_ids=self.channel_map.channel_ids(),
                element_ids=self.channel_map.element_ids(),
                iq=iq,
            )

    def _recv_exact(self, n_samp: int, *, timeout_s: float) -> np.ndarray:
        buf = np.zeros((self.n_chan, n_samp), dtype=np.complex64)
        got = 0
        deadline = time.monotonic() + timeout_s
        while got < n_samp:
            remain = deadline - time.monotonic()
            if remain <= 0:
                raise SdrError("live recv timed out")
            view = buf[:, got:]
            n = self._recv_into(view, timeout_s=remain)
            if n <= 0:
                raise SdrError("live recv returned no samples")
            got += int(n)
        return buf

    def _recv_into(self, view: np.ndarray, *, timeout_s: float) -> int:
        streamer = self._streamer
        md = self._md
        try:
            n = streamer.recv(view, md, timeout=timeout_s)
        except TypeError:
            chans = [np.ascontiguousarray(view[i]) for i in range(self.n_chan)]
            n = streamer.recv(chans, md, timeout=timeout_s)
            for i, ch in enumerate(chans):
                view[i, : ch.size] = ch
        self._raise_if_rx_error()
        return int(n)

    def _raise_if_rx_error(self) -> None:
        md = self._md
        err = getattr(md, "error_code", None)
        none = getattr(self._uhd.types, "RXMetadataErrorCode", None)
        none_val = getattr(none, "none", 0) if none is not None else 0
        if err is not None and err != none_val:
            raise SdrError(f"UHD RX error: {err}")
