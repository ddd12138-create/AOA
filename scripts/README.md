# scripts

Process launchers. **No UHD, MUSIC, or Qt implementation in this skeleton.**

## Planned processes

| Process | Role | Notes |
| --- | --- | --- |
| worker | `sdr` → `detect` → `aoa` in one process | Must support `--replay` with no device |
| host | PySide6 UI | ZMQ client only; no MUSIC/UHD on GUI thread |

## Planned CLI (do not invent extra flags that contradict interfaces)

```text
python -m sdr --replay tests/golden/theta30_m4
python scripts/worker.py --replay tests/golden/theta30_m4 --array configs/array_uca_m4.yaml
python scripts/host.py --zmq tcp://127.0.0.1:5556
```

Addresses and JSON envelopes: [docs/interfaces.md](../docs/interfaces.md). How to run: [docs/runbook.md](../docs/runbook.md).
