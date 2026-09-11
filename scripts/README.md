# scripts

Process launchers. Worker runs MUSIC; host is a ZMQ client only.

| Process | Role | Notes |
| --- | --- | --- |
| worker | `sdr` → detect placeholder → `aoa.MusicEstimator` → ZMQ | `--replay` needs no device / no UHD |
| host | PySide6 UI | ZMQ client only; no MUSIC/UHD on GUI thread |

```text
python -m sdr --replay tests/golden/theta30_m4
python scripts/worker.py --replay tests/golden/theta30_m4
python scripts/worker.py --replay tests/golden/theta30_m4 --array configs/array_uca_m4_sim.yaml
python scripts/worker.py --replay tests/golden/theta30_m4 --array configs/array_uca_m4.yaml
python scripts/worker.py --live --config configs/channel_map.yaml --array configs/array_uca_m4.yaml
python scripts/worker.py --live --config configs/channel_map.yaml --array configs/array_uca_m4.yaml --save captures/x310_m4
python scripts/host.py --zmq tcp://127.0.0.1:5556
```

`--replay` defaults `--array` to `configs/array_uca_m4_sim.yaml`. `--live` defaults to `configs/array_uca_m4.yaml`. If that hardware file still has `R_m: null`, worker still PUBs iq/detect, does not PUB aoa, and keeps `status.state=running` with a missing-`R_m` `detail`. Identity calib (`calib/identity.yaml`) sets `status.uncalibrated=true`.

Worker PUB `tcp://127.0.0.1:5556` (topic `iq` / `detect` / `aoa` / `status`), REP `tcp://127.0.0.1:5557` (`tune` / `start` / `stop`). detect is a whole-frame burst placeholder until `detect/` exists. Addresses and JSON: [docs/interfaces.md](../docs/interfaces.md). How to run: [docs/runbook.md](../docs/runbook.md).

## Local check (θ ≈ 30°)

1. Worker replay (MUSIC in this process):

   ```text
   python scripts/worker.py --replay tests/golden/theta30_m4
   ```

2. Host (other terminal; polar ray from `aoa.azimuth_deg` only):

   ```text
   python scripts/host.py
   ```

Expect the polar pointer near **30°**, `azimuth_deg` ≈ 30, red **UNCALIBRATED** banner, `GeoFix.valid=false`. Headless:

```text
pytest tests/test_worker_replay_theta30.py tests/test_aoa_theta30.py
```
