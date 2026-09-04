"""Display widgets. Plots consume worker JSON only — no MUSIC / UHD / geo fix."""

from __future__ import annotations

import math
from typing import Any

import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from host.protocol import as_float, format_db, format_hz, geo_fix_valid, status_detail, wrap_azimuth_deg


def _mono(point: int = 11, bold: bool = False) -> QFont:
    font = QFont("Consolas")
    if font.family() != "Consolas":
        font = QFont("monospace")
    font.setPointSize(point)
    font.setBold(bold)
    return font


class UncalBanner(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("uncalBanner")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._label = QLabel("未校准  UNCALIBRATED")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self._label)
        self.setVisible(False)

    def set_uncalibrated(self, flag: bool | None) -> None:
        self.setVisible(bool(flag))


class DeviceStatusPanel(QGroupBox):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("设备 / status", parent)
        self.link = QLabel("未连接")
        self.state = QLabel("—")
        self.replay = QLabel("—")
        self.m_chan = QLabel("—")
        self.fc = QLabel("—")
        self.detail = QLabel("—")
        self.detail.setWordWrap(True)
        self.detect = QLabel("—")
        self.cmd = QLabel("—")
        self.cmd.setWordWrap(True)

        self.fc_edit = QLineEdit()
        self.fc_edit.setPlaceholderText("fc_hz（例如 2400000000）")
        self.fs_edit = QLineEdit()
        self.fs_edit.setPlaceholderText("fs_hz 可选")
        self.gain_edit = QLineEdit()
        self.gain_edit.setPlaceholderText("gain_db 可选")
        self.btn_start = QPushButton("start")
        self.btn_stop = QPushButton("stop")
        self.btn_tune = QPushButton("tune")

        form = QFormLayout()
        form.addRow("连接", self.link)
        form.addRow("state", self.state)
        form.addRow("replay", self.replay)
        form.addRow("M", self.m_chan)
        form.addRow("fc_hz", self.fc)
        form.addRow("detail", self.detail)
        form.addRow("detect", self.detect)
        form.addRow("命令应答", self.cmd)

        buttons = QHBoxLayout()
        buttons.addWidget(self.btn_start)
        buttons.addWidget(self.btn_stop)
        buttons.addWidget(self.btn_tune)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.fc_edit)
        layout.addWidget(self.fs_edit)
        layout.addWidget(self.gain_edit)
        layout.addLayout(buttons)

        for label in (
            self.link,
            self.state,
            self.replay,
            self.m_chan,
            self.fc,
            self.detail,
            self.detect,
            self.cmd,
        ):
            label.setFont(_mono(10))

    def set_disconnected(self) -> None:
        self.link.setText("未连接")
        self.link.setStyleSheet("color: #ffab91;")
        self.state.setText("—")
        self.replay.setText("—")
        self.m_chan.setText("—")
        self.fc.setText("—")
        self.detail.setText("等待 worker PUB tcp://…:5556")
        self.detect.setText("—")

    def set_connected_idle(self, stale: bool) -> None:
        self.link.setText("已连接（无新数据）" if stale else "已连接")
        self.link.setStyleSheet("color: #a5d6a7;")

    def apply_status(self, msg: dict[str, Any]) -> None:
        state = str(msg.get("state") or "—")
        self.state.setText(state)
        colors = {"idle": "#bdbdbd", "running": "#81c784", "error": "#ef9a9a"}
        self.state.setStyleSheet(f"color: {colors.get(state, '#eeeeee')};")
        replay = msg.get("replay")
        self.replay.setText("true" if replay is True else "false" if replay is False else "—")
        self.m_chan.setText(str(msg["M"]) if isinstance(msg.get("M"), int) else "—")
        self.fc.setText(format_hz(msg.get("fc_hz")))
        self.detail.setText(status_detail(msg) or "—")

    def apply_detect(self, msg: dict[str, Any]) -> None:
        band = msg.get("band") if isinstance(msg.get("band"), str) else "—"
        snr = as_float(msg.get("snr_db"))
        snr_s = f"{snr:.1f} dB" if snr is not None else "—"
        self.detect.setText(f"band={band}  snr_db={snr_s}")

    def apply_cmd_reply(self, reply: dict[str, Any]) -> None:
        if reply.get("ok") is True:
            self.cmd.setText("ok")
            self.cmd.setStyleSheet("color: #a5d6a7;")
            return
        err = reply.get("error")
        self.cmd.setText(str(err) if err else "ok=false")
        self.cmd.setStyleSheet("color: #ef9a9a;")

    def tune_fields(self) -> dict[str, Any]:
        def _opt_float(edit: QLineEdit) -> float | None:
            text = edit.text().strip()
            if not text:
                return None
            return float(text)

        return {
            "cmd": "tune",
            "fc_hz": _opt_float(self.fc_edit),
            "fs_hz": _opt_float(self.fs_edit),
            "gain_db": _opt_float(self.gain_edit),
        }


class IqSummaryWidget(QGroupBox):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("IQ 幅度摘要", parent)
        self.meta = QLabel("无 IQ")
        self.meta.setFont(_mono(10))
        self.meta.setWordWrap(True)
        self.rms = QLabel("—")
        self.rms.setFont(_mono(10))
        self.rms.setWordWrap(True)

        self.plot = pg.PlotWidget()
        self.plot.setMinimumHeight(140)
        self.plot.setTitle("|IQ| ch0（摘要，非频谱估计）")
        self.plot.setLabel("left", "幅度")
        self.plot.setLabel("bottom", "样本（抽稀）")
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        self._curve = self.plot.plot([], [], pen=pg.mkPen("#4fc3f7", width=1.5))

        layout = QVBoxLayout(self)
        layout.addWidget(self.meta)
        layout.addWidget(self.rms)
        layout.addWidget(self.plot)

    def apply_summary(self, summary: dict[str, Any]) -> None:
        header = summary.get("header") if isinstance(summary.get("header"), dict) else {}
        n_chan = summary.get("n_chan")
        n_samp = summary.get("n_samp")
        fc = format_hz(header.get("fc_hz"))
        fs = format_hz(header.get("fs_hz"))
        frame_id = header.get("frame_id")
        self.meta.setText(
            f"frame_id={frame_id}  n_chan={n_chan}  n_samp={n_samp}  "
            f"fc={fc}  fs={fs}  dtype={header.get('dtype')}"
        )
        rms_lin = summary.get("rms_lin") if isinstance(summary.get("rms_lin"), list) else []
        element_ids = summary.get("element_ids") if isinstance(summary.get("element_ids"), list) else []
        channel_ids = summary.get("channel_ids") if isinstance(summary.get("channel_ids"), list) else []
        parts = []
        for i, rms in enumerate(rms_lin):
            if not isinstance(rms, (int, float)):
                continue
            ch = channel_ids[i] if i < len(channel_ids) else i
            el = element_ids[i] if i < len(element_ids) else "?"
            parts.append(f"ch{ch}/el{el}  {format_db(float(rms))}")
        self.rms.setText("  |  ".join(parts) if parts else "无幅度（缺 IQ 体或长度不符）")
        trace = summary.get("mag_trace") if isinstance(summary.get("mag_trace"), list) else []
        ys = [float(v) for v in trace if isinstance(v, (int, float))]
        self._curve.setData(list(range(len(ys))), ys)


class MusicPolarWidget(QGroupBox):
    """Array-frame polar view 0–360°. Draws the AOA ray only. Never plots lat/lon."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("MUSIC 极坐标（阵列方位 0–360°）", parent)
        self.plot = pg.PlotWidget()
        self.plot.setAspectLocked(True)
        self.plot.hideAxis("bottom")
        self.plot.hideAxis("left")
        self.plot.setXRange(-1.25, 1.25)
        self.plot.setYRange(-1.25, 1.25)
        self.plot.setMenuEnabled(False)
        self.plot.setMinimumSize(280, 280)
        self._ray = self.plot.plot([], [], pen=pg.mkPen("#ffee58", width=3))
        self._peaks = pg.ScatterPlotItem(size=9, brush=pg.mkBrush("#81d4fa"), pen=None)
        self.plot.addItem(self._peaks)
        self._flyer_items: list[Any] = []
        self._draw_grid()

        layout = QVBoxLayout(self)
        layout.addWidget(self.plot)

    def _draw_grid(self) -> None:
        steps = 96
        for radius in (0.33, 0.66, 1.0):
            xs = [radius * math.cos(2 * math.pi * i / steps) for i in range(steps + 1)]
            ys = [radius * math.sin(2 * math.pi * i / steps) for i in range(steps + 1)]
            self.plot.plot(xs, ys, pen=pg.mkPen("#546e7a", width=1))
        for deg in range(0, 360, 30):
            rad = math.radians(deg)
            self.plot.plot(
                [0.0, math.cos(rad)],
                [0.0, math.sin(rad)],
                pen=pg.mkPen("#37474f", width=1),
            )
            label = pg.TextItem(f"{deg}°", color="#90a4ae", anchor=(0.5, 0.5))
            label.setPos(1.16 * math.cos(rad), 1.16 * math.sin(rad))
            self.plot.addItem(label)
        origin = pg.TextItem("0° 阵列轴", color="#cfd8dc", anchor=(0.0, 0.5))
        origin.setPos(1.02, 0.08)
        self.plot.addItem(origin)

    def apply_aoa(self, result: dict[str, Any]) -> None:
        az = wrap_azimuth_deg(result.get("azimuth_deg"))
        if az is None:
            self._ray.setData([], [])
        else:
            rad = math.radians(az)
            self._ray.setData([0.0, 0.96 * math.cos(rad)], [0.0, 0.96 * math.sin(rad)])
        self._apply_peaks(result.get("music_spectrum_summary"))
        self._forbid_flyer_if_invalid(result)

    def _apply_peaks(self, summary: Any) -> None:
        spots: list[dict[str, Any]] = []
        if isinstance(summary, dict):
            peaks = summary.get("peaks")
            if isinstance(peaks, list):
                p_vals = [
                    as_float(p.get("p_db"))
                    for p in peaks
                    if isinstance(p, dict)
                ]
                finite = [p for p in p_vals if p is not None]
                lo = min(finite) if finite else 0.0
                hi = max(finite) if finite else 1.0
                span = (hi - lo) or 1.0
                for peak in peaks:
                    if not isinstance(peak, dict):
                        continue
                    theta = wrap_azimuth_deg(peak.get("theta_deg"))
                    pdb = as_float(peak.get("p_db"))
                    if theta is None:
                        continue
                    t = 0.5 if pdb is None else (pdb - lo) / span
                    r = 0.45 + 0.45 * t
                    rad = math.radians(theta)
                    spots.append({"pos": (r * math.cos(rad), r * math.sin(rad))})
        self._peaks.setData(spots)

    def _forbid_flyer_if_invalid(self, result: dict[str, Any]) -> None:
        # Single-station GeoFix is invalid: never create a lat/lon marker.
        if not geo_fix_valid(result):
            self.clear_flyer_layer()

    def clear_flyer_layer(self) -> None:
        for item in self._flyer_items:
            self.plot.removeItem(item)
        self._flyer_items.clear()


class AzimuthReadout(QGroupBox):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("当前 azimuth_deg", parent)
        self.value = QLabel("—")
        self.value.setObjectName("azimuthValue")
        self.value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.value.setFont(QFont("Segoe UI", 28, QFont.Weight.Bold))
        self.extra = QLabel("阵列坐标系 · 非真北 · 非经纬度")
        self.extra.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.geo = QLabel("GeoFix.valid=false：禁止绘制飞手经纬度")
        self.geo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.geo.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addWidget(self.value)
        layout.addWidget(self.extra)
        layout.addWidget(self.geo)

    def apply_aoa(self, result: dict[str, Any]) -> None:
        az = wrap_azimuth_deg(result.get("azimuth_deg"))
        self.value.setText("—" if az is None else f"{az:.2f}°")
        conf = as_float(result.get("confidence"))
        k_est = result.get("K_est")
        bits = []
        if conf is not None:
            bits.append(f"confidence={conf:.2f}")
        if isinstance(k_est, int):
            bits.append(f"K_est={k_est}")
        elev = result.get("elevation_deg")
        bits.append("elevation_deg=null" if elev is None else f"elevation_deg={elev}")
        self.extra.setText("  ·  ".join(bits) if bits else "阵列坐标系")
        if geo_fix_valid(result):
            self.geo.setText("GeoFix.valid=true（多站预留，本 MVP 仍不绘制飞手坐标）")
        else:
            self.geo.setText("GeoFix.valid=false：禁止绘制飞手经纬度")


class StationTwoLayer(QGroupBox):
    """Reserved second-station / intersection overlay. Disabled on purpose."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("第二站图层（预留）", parent)
        note = QLabel(
            "多站交汇未部署。本图层禁用，不画第二站，也不把单站 AOA 画成飞手点。"
        )
        note.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addWidget(note)
        self.setEnabled(False)
        self.setToolTip("第二站 / 交汇图层已预留并禁用")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

