"""Host process entry: PySide6 ZMQ client. No MUSIC / UHD in this process."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from host.main import main

if __name__ == "__main__":
    raise SystemExit(main())
