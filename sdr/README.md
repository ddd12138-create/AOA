# sdr

Owns USRP acquisition and file replay. Produces `IqFrame` as defined in [docs/interfaces.md](../docs/interfaces.md).

## Scope

- Live capture from one X310 + two TwinRX (M=4), with LO share required.
- `--replay` of `<stem>.npy` + `<stem>.meta.json` so development works with no hardware.
- Channel order of IQ rows must match `channel_ids` / `element_ids` / `a(θ)` row order.

## Out of scope

- MUSIC, detection, Qt windows, GeoFix.
- Editing [docs/interfaces.md](../docs/interfaces.md) or anything under `阵列天线/`.
- RF switching / polling unused UCA elements.

## CLI (not implemented in this skeleton)

```text
python -m sdr --replay path/to/stem
python -m sdr --live --config configs/channel_map.yaml
```

`--replay` is mandatory in the live CLI as well (the flag must exist; live mode is optional). See [docs/runbook.md](../docs/runbook.md).
