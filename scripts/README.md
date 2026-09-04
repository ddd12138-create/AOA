# scripts

Process launchers. Worker is implemented; host/Qt is not in this package.

| Process | Role | Notes |
| --- | --- | --- |
| worker | `sdr` → detect/aoa hooks → ZMQ | `--replay` needs no device / no UHD |
| host | PySide6 UI (not here) | ZMQ client only; no MUSIC/UHD on GUI thread |

```text
python -m sdr --replay tests/golden/theta30_m4
python scripts/worker.py --replay tests/golden/theta30_m4 --array configs/array_uca_m4.yaml
python scripts/worker.py --live --config configs/channel_map.yaml --array configs/array_uca_m4.yaml
```

Worker PUB `tcp://127.0.0.1:5556` (topic `iq` / `status`), REP `tcp://127.0.0.1:5557` (`tune` / `start` / `stop`). detect/aoa are empty callbacks until those packages exist. Addresses and JSON: [docs/interfaces.md](../docs/interfaces.md). How to run: [docs/runbook.md](../docs/runbook.md).
