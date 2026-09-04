# host

PySide6 (Qt 6) + pyqtgraph UI process. Independent from the worker. Not C++ Qt, not a web UI.

## Run

```text
python scripts/host.py --zmq tcp://127.0.0.1:5556
```

- SUB: `--zmq` (default `tcp://127.0.0.1:5556`)
- Command REQ: same host, port + 1 (`tcp://127.0.0.1:5557`)

The window opens even if the worker is down; the device panel shows **未连接**.

## Scope

- Subscribe to worker topics `iq`, `detect`, `aoa`, `status`.
- Send `tune` / `start` / `stop` on the command socket.
- Show device/status, IQ amplitude summary, MUSIC polar 0–360°, `azimuth_deg`.
- `AoAResult` draws the array-frame azimuth ray only.
- `geo_fix.valid == false`: never plot flyer lat/lon.
- `uncalibrated == true`: red **UNCALIBRATED** banner.
- Second-station layer is reserved and disabled.

## Hard rules

- Do **not** run MUSIC, UHD, or heavy numpy AOA on the GUI thread (or in this process).
- Do **not** turn a single-station `AoAResult` into a map point.
