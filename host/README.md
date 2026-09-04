# host

PySide6 (Qt 6) + pyqtgraph UI process. Not C++ Qt, not a web UI.

## Scope

- Subscribe to worker ZMQ topics (`iq`, `detect`, `aoa`, `status`).
- Send `tune` / `start` / `stop` on the command socket.
- Display azimuth (array frame; optional north-converted value). Polar / spectrum plots only.

## Hard rules

- Do **not** run MUSIC, UHD, or heavy numpy AOA on the GUI thread. Compute lives in the worker process.
- Do **not** plot a flyer lat/lon from a single-station `AoAResult`. `GeoFix` is invalid until multi-station geo exists.

## Out of scope (this skeleton)

- Any window, widget, or slot implementation.
