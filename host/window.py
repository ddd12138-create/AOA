"""Main window: ZMQ display + commands. GUI thread does no MUSIC / UHD / DF."""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QSplitter, QVBoxLayout, QWidget

from host.widgets import (
    AzimuthReadout,
    DeviceStatusPanel,
    IqSummaryWidget,
    MusicPolarWidget,
    StationTwoLayer,
    UncalBanner,
)
from host.zmq_bridge import ZmqBridge

_STALE_S = 5.0


class MainWindow(QMainWindow):
    def __init__(self, sub_endpoint: str, cmd_endpoint: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("AOA Host")
        self.resize(1180, 760)

        self._sub_endpoint = sub_endpoint
        self._cmd_endpoint = cmd_endpoint
        self._last_rx_mono: float | None = None
        self._seen_worker = False
        self._last_uncal: bool | None = None

        self.banner = UncalBanner()
        self.device = DeviceStatusPanel()
        self.iq = IqSummaryWidget()
        self.polar = MusicPolarWidget()
        self.azimuth = AzimuthReadout()
        self.station2 = StationTwoLayer()

        self.device.set_disconnected()

        left = QVBoxLayout()
        left.addWidget(self.device)
        left.addWidget(self.station2)
        left.addStretch(1)
        left_w = QWidget()
        left_w.setLayout(left)

        plots = QSplitter(Qt.Orientation.Horizontal)
        plots.addWidget(self.iq)
        plots.addWidget(self.polar)
        plots.setStretchFactor(0, 1)
        plots.setStretchFactor(1, 1)

        right = QVBoxLayout()
        right.addWidget(self.azimuth)
        right.addWidget(plots, 1)
        right_w = QWidget()
        right_w.setLayout(right)

        body = QHBoxLayout()
        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(left_w)
        split.addWidget(right_w)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([320, 860])
        body.addWidget(split)

        root = QVBoxLayout()
        root.addWidget(self.banner)
        root.addLayout(body, 1)
        central = QWidget()
        central.setLayout(root)
        self.setCentralWidget(central)
        self.statusBar().showMessage(f"SUB {sub_endpoint}  ·  CMD {cmd_endpoint}  ·  无 worker 时可空等")

        self.bridge = ZmqBridge(sub_endpoint, cmd_endpoint, self)
        self.bridge.status_msg.connect(self._on_status)
        self.bridge.aoa_msg.connect(self._on_aoa)
        self.bridge.detect_msg.connect(self._on_detect)
        self.bridge.iq_summary.connect(self._on_iq)
        self.bridge.cmd_reply.connect(self._on_cmd_reply)
        self.bridge.bridge_error.connect(self._on_bridge_error)

        self.device.btn_start.clicked.connect(lambda: self._send_cmd("start"))
        self.device.btn_stop.clicked.connect(lambda: self._send_cmd("stop"))
        self.device.btn_tune.clicked.connect(self._send_tune)

        self._watch = QTimer(self)
        self._watch.setInterval(500)
        self._watch.timeout.connect(self._refresh_link)
        self._watch.start()

        self.bridge.start()

    def closeEvent(self, event) -> None:  # noqa: N802
        self._watch.stop()
        self.bridge.stop()
        self.bridge.wait(1500)
        event.accept()

    def _mark_rx(self) -> None:
        self._last_rx_mono = time.monotonic()
        self._seen_worker = True
        self._refresh_link()

    def _refresh_link(self) -> None:
        if not self._seen_worker or self._last_rx_mono is None:
            self.device.set_disconnected()
            self.statusBar().showMessage(
                f"未连接  ·  SUB {self._sub_endpoint}  ·  CMD {self._cmd_endpoint}"
            )
            return
        stale = (time.monotonic() - self._last_rx_mono) > _STALE_S
        self.device.set_connected_idle(stale)
        extra = "无新数据" if stale else "收数中"
        uncal = "  ·  UNCALIBRATED" if self._last_uncal else ""
        self.statusBar().showMessage(f"已连接（{extra}）{uncal}  ·  SUB {self._sub_endpoint}")

    def _on_status(self, msg: object) -> None:
        if not isinstance(msg, dict):
            return
        self._mark_rx()
        self.device.apply_status(msg)
        flag = msg.get("uncalibrated")
        self._last_uncal = bool(flag) if isinstance(flag, bool) else None
        self.banner.set_uncalibrated(self._last_uncal is True)

    def _on_aoa(self, msg: object) -> None:
        if not isinstance(msg, dict):
            return
        self._mark_rx()
        self.polar.apply_aoa(msg)
        self.azimuth.apply_aoa(msg)

    def _on_detect(self, msg: object) -> None:
        if not isinstance(msg, dict):
            return
        self._mark_rx()
        self.device.apply_detect(msg)

    def _on_iq(self, summary: object) -> None:
        if not isinstance(summary, dict):
            return
        self._mark_rx()
        self.iq.apply_summary(summary)

    def _on_cmd_reply(self, reply: object) -> None:
        if not isinstance(reply, dict):
            return
        self.device.apply_cmd_reply(reply)

    def _on_bridge_error(self, text: str) -> None:
        self.device.cmd.setText(text)
        self.device.cmd.setStyleSheet("color: #ef9a9a;")

    def _send_cmd(self, name: str) -> None:
        self.bridge.request(
            {"cmd": name, "fc_hz": None, "fs_hz": None, "gain_db": None}
        )

    def _send_tune(self) -> None:
        try:
            payload = self.device.tune_fields()
        except ValueError:
            self.device.apply_cmd_reply({"ok": False, "error": "tune 参数必须是数字"})
            return
        self.bridge.request(payload)
