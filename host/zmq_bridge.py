"""Background ZMQ SUB + REQ. The Qt GUI thread never touches sockets."""

from __future__ import annotations

import queue
import threading
from typing import Any

from PySide6.QtCore import QThread, Signal

from host.protocol import decode_json_bytes, summarize_iq, topic_of


class ZmqBridge(QThread):
    status_msg = Signal(object)
    aoa_msg = Signal(object)
    detect_msg = Signal(object)
    iq_summary = Signal(object)
    cmd_reply = Signal(object)
    bridge_error = Signal(str)

    def __init__(self, sub_endpoint: str, cmd_endpoint: str, parent=None) -> None:
        super().__init__(parent)
        self._sub_endpoint = sub_endpoint
        self._cmd_endpoint = cmd_endpoint
        self._stop = threading.Event()
        self._cmds: queue.Queue[dict[str, Any]] = queue.Queue()

    def request(self, payload: dict[str, Any]) -> None:
        self._cmds.put(payload)

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        try:
            import zmq
        except ImportError:
            self.bridge_error.emit("pyzmq 未安装，无法连接 worker")
            return

        ctx = zmq.Context()
        sub = ctx.socket(zmq.SUB)
        sub.setsockopt(zmq.LINGER, 0)
        sub.setsockopt(zmq.RCVHWM, 8)
        sub.setsockopt(zmq.RCVTIMEO, 100)
        sub.connect(self._sub_endpoint)
        for name in (b"iq", b"detect", b"aoa", b"status"):
            sub.setsockopt(zmq.SUBSCRIBE, name)

        req = self._open_req(ctx, zmq)
        try:
            while not self._stop.is_set():
                req = self._drain_commands(ctx, zmq, req)
                try:
                    frames = sub.recv_multipart()
                except zmq.Again:
                    continue
                except zmq.ZMQError as exc:
                    if self._stop.is_set():
                        break
                    self.bridge_error.emit(f"SUB 错误: {exc}")
                    continue
                self._dispatch(frames)
        finally:
            sub.close(0)
            req.close(0)
            ctx.term()

    def _open_req(self, ctx: Any, zmq: Any) -> Any:
        req = ctx.socket(zmq.REQ)
        req.setsockopt(zmq.LINGER, 0)
        req.setsockopt(zmq.RCVTIMEO, 400)
        req.setsockopt(zmq.SNDTIMEO, 400)
        req.connect(self._cmd_endpoint)
        return req

    def _reset_req(self, ctx: Any, zmq: Any, req: Any) -> Any:
        req.close(0)
        return self._open_req(ctx, zmq)

    def _drain_commands(self, ctx: Any, zmq: Any, req: Any) -> Any:
        try:
            cmd = self._cmds.get_nowait()
        except queue.Empty:
            return req
        try:
            req.send_json(cmd)
            reply = req.recv_json()
            if not isinstance(reply, dict):
                reply = {"ok": False, "error": "命令应答不是 JSON 对象"}
            self.cmd_reply.emit(reply)
            return req
        except zmq.Again:
            self.cmd_reply.emit({"ok": False, "error": "命令口超时（worker 未响应）"})
            return self._reset_req(ctx, zmq, req)
        except Exception as exc:  # noqa: BLE001 — surface any socket failure
            self.cmd_reply.emit({"ok": False, "error": str(exc)})
            return self._reset_req(ctx, zmq, req)

    def _dispatch(self, frames: list[bytes]) -> None:
        topic = topic_of(frames)
        if topic is None or len(frames) < 2:
            return
        payload = decode_json_bytes(frames[1])
        if payload is None:
            return
        if topic == "status":
            self.status_msg.emit(payload)
        elif topic == "aoa":
            self.aoa_msg.emit(payload)
        elif topic == "detect":
            self.detect_msg.emit(payload)
        elif topic == "iq":
            blob = frames[2] if len(frames) >= 3 and isinstance(frames[2], (bytes, bytearray)) else b""
            self.iq_summary.emit(summarize_iq(payload, bytes(blob)))
