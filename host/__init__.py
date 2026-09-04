"""PySide6 host UI process.

Independent process: SUB worker PUB, REQ on the command socket.
Must not run MUSIC, UHD, or heavy numpy DF on the GUI thread.
"""

from host.main import main

__all__ = ["main"]
