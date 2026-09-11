# tests

## θ = 30° acceptance (algorithm regression, not field spec)

1. `python -m sim` writes `golden/theta30_m4.npy` + `golden/theta30_m4.meta.json`.
2. `MusicEstimator` with `configs/array_uca_m4_sim.yaml` and `calib/identity.yaml`.
3. Pass: `|AoAResult.azimuth_deg - 30| ≤ 2°` at high SNR (tighter than the 5° RMS field goal).

```text
pytest tests/test_aoa_theta30.py tests/test_worker_replay_theta30.py tests/test_calib_theta30.py
```

Do not implement MUSIC inside the test. Fixture `R_m: null` must refuse azimuth.

Worker `--replay tests/golden/theta30_m4` (default `configs/array_uca_m4_sim.yaml`) must PUB topic `aoa` with `|azimuth_deg - 30| ≤ 2°` so host polar points near 30°. Hardware `configs/array_uca_m4.yaml` (`R_m: null`) must not emit `aoa`; `status.state` stays `running` with a missing-`R_m` `detail`, and iq/detect still PUB.

## Channel calib (known source)

`python -m calib --replay tests/golden/theta30_m4 --theta-deg 30 --array configs/array_uca_m4_sim.yaml --out <tmp.yaml>` must write `status=calibrated`. `MusicEstimator` with that file on the same golden stem must keep `|azimuth_deg - 30| ≤ 2°` and `uncalibrated=false`. A channel multiplied by `e^{jπ/2}` must be pulled back to the same bound. `R_m: null` refuses calibration. `calib/identity.yaml` stays `status=identity`.

## Out of scope

- Hardware-in-the-loop in this skeleton.
- Asserting a valid `GeoFix` from one station.
