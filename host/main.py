"""Host process: PySide6 window + ZMQ client. No MUSIC / UHD in this process."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from host.protocol import DEFAULT_SUB, derive_command_endpoint


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AOA host UI (ZMQ subscriber, no DF)")
    parser.add_argument(
        "--zmq",
        default=DEFAULT_SUB,
        help=f"worker PUB endpoint (default {DEFAULT_SUB})",
    )
    return parser


def _package_dir(name: str) -> Path | None:
    import importlib.util

    spec = importlib.util.find_spec(name)
    if spec is None or not spec.origin:
        return None
    return Path(spec.origin).resolve().parent


def prepare_pyside6_runtime() -> None:
    """Load pip PySide6 Qt DLLs before Anaconda bins can shadow them.

    On Anaconda, ``Library\\bin`` often provides an incompatible zlib/ICU and
    ``import PySide6.QtWidgets`` fails with WinError 127. Isolate PATH just
    long enough to import Qt, then restore it for numpy / pyzmq.
    """
    os.environ.setdefault("PYQTGRAPH_QT_LIB", "PySide6")
    extra = [str(p) for p in (_package_dir("PySide6"), _package_dir("shiboken6")) if p]
    if not extra:
        return
    original = os.environ.get("PATH", "")
    windir = os.environ.get("WINDIR", r"C:\Windows")
    isolated = extra + [
        str(Path(windir) / "System32"),
        windir,
    ]
    os.environ["PATH"] = os.pathsep.join(isolated)
    if hasattr(os, "add_dll_directory"):
        for item in isolated:
            os.add_dll_directory(item)
    try:
        from PySide6 import QtCore  # noqa: F401
        from PySide6 import QtGui  # noqa: F401
        from PySide6 import QtWidgets  # noqa: F401
    finally:
        os.environ["PATH"] = os.pathsep.join(extra + original.split(os.pathsep))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    sub = args.zmq
    cmd = derive_command_endpoint(sub)

    prepare_pyside6_runtime()

    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer
    import pyqtgraph as pg

    from host.window import MainWindow

    pg.setConfigOptions(antialias=True, background="#121214", foreground="#e0e0e0")

    app = QApplication(sys.argv)
    app.setApplicationName("AOA Host")
    app.setStyleSheet(
        """
        QMainWindow, QWidget { background: #121214; color: #e8e8e8; }
        QGroupBox {
            border: 1px solid #3a3a42;
            border-radius: 4px;
            margin-top: 12px;
            padding: 8px;
            font-weight: 600;
        }
        QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
        QLineEdit {
            background: #1e1e24; border: 1px solid #45454f; padding: 4px; color: #eee;
        }
        QPushButton {
            background: #2a2a32; border: 1px solid #555; padding: 6px 12px;
        }
        QPushButton:hover { background: #3a3a44; }
        QStatusBar { color: #b0b0b0; }
        #uncalBanner {
            background: #c62828;
            color: #fff;
            border: 2px solid #ff8a80;
        }
        #azimuthValue { color: #ffd54f; }
        """
    )
    win = MainWindow(sub, cmd)
    win.show()

    if os.environ.get("AOA_HOST_SMOKE") == "1":
        QTimer.singleShot(400, app.quit)

    return int(app.exec())


if __name__ == "__main__":
    raise SystemExit(main())
