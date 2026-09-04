# tests

## θ = 30° acceptance (algorithm regression, not field spec)

1. `python -m sim` writes `golden/theta30_m4.npy` + `golden/theta30_m4.meta.json`.
2. `MusicEstimator` with `configs/array_uca_m4_sim.yaml` and `calib/identity.yaml`.
3. Pass: `|AoAResult.azimuth_deg - 30| ≤ 2°` at high SNR (tighter than the 5° RMS field goal).

```text
pytest tests/test_aoa_theta30.py
```

Do not implement MUSIC inside the test. Fixture `R_m: null` must refuse azimuth.

## Out of scope

- Hardware-in-the-loop in this skeleton.
- Asserting a valid `GeoFix` from one station.
