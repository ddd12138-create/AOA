"""One X310 + two TwinRX (M=4) live capture. UHD is imported only when opening the radio."""

from __future__ import annotations

import threading
import time
from types import ModuleType

import numpy as np

from sdr.channel_map import ChannelMap, assert_live_allowed
from sdr.errors import SdrError
from sdr.iqframe import IqFrame, make_iq_frame

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
        self._open_radio()

    def _open_radio(self) -> None:
        uhd = self._uhd
        args = self.channel_map.device_args_resolved()
        self._usrp = uhd.usrp.MultiUSRP(args)
        spec = self.channel_map.rx_subdev_spec()
        try:
            self._usrp.set_rx_subdev_spec(spec)
        except TypeError:
            spec_cls = getattr(uhd.usrp, "SubdevSpec", None)
            if spec_cls is None:
                raise
            self._usrp.set_rx_subdev_spec(spec_cls(spec))

        for ch in range(self.n_chan):
            self._usrp.set_rx_rate(self.fs_hz, ch)
            self._usrp.set_rx_freq(_tune_request(uhd, self.fc_hz), ch)
            self._usrp.set_rx_gain(self.gain_db, ch)

        st_args = uhd.usrp.StreamArgs("fc32", "sc16")
        st_args.channels = list(range(self.n_chan))
        self._streamer = self._usrp.get_rx_stream(st_args)
        self._md = uhd.types.RXMetadata()

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
            for ch in range(self.n_chan):
                if fs_hz is not None:
                    self._usrp.set_rx_rate(self.fs_hz, ch)
                if fc_hz is not None:
                    self._usrp.set_rx_freq(_tune_request(self._uhd, self.fc_hz), ch)
                if gain_db is not None:
                    self._usrp.set_rx_gain(self.gain_db, ch)
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
        cmd = uhd.types.StreamCMD(uhd.types.StreamMode.start_continuous)
        cmd.stream_now = True
        self._streamer.issue_stream_cmd(cmd)
        self._streaming = True

    def _stop_unlocked(self) -> None:
        if not self._streaming:
            return
        uhd = self._uhd
        cmd = uhd.types.StreamCMD(uhd.types.StreamMode.stop_continuous)
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
