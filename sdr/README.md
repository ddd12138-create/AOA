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

## CLI

```text
python -m sdr --replay path/to/stem
python -m sdr --live --config configs/channel_map.yaml
python -m sdr --live --config configs/channel_map.yaml --save path/to/stem
python -m sdr --replay path/to/stem --save path/to/copy
```

`--replay` is always on the parser (live is optional). It loads `<stem>.npy` + `<stem>.meta.json` and does not import UHD. `--live` is one X310 / 4 TwinRX channels in `channel_map.yaml` order (`A:0→1` … `B:1→7`) and is refused unless `lo_share` is true. Live programs TwinRX LO with `set_rx_lo_source(..., "all", chan)`: ch0 internal+export, ch1 companion, ch2 external, ch3 companion. Slot B `lo_locked` false is treated as missing board-to-board MMCX and aborts. `--save` writes the current IqFrame as `<stem>.npy` + `<stem>.meta.json`.

Worker ZMQ entry: `python scripts/worker.py --replay path/to/stem` (same `--save`). Hardware `--array configs/array_uca_m4.yaml` with `R_m: null` still PUBs iq/detect; it does not PUB aoa. See [docs/runbook.md](../docs/runbook.md).
