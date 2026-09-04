# tests

## θ = 30° acceptance (algorithm regression, not field spec)

1. `sim/` writes `golden/theta30_m4.npy` + `golden/theta30_m4.meta.json`.
2. Worker `--replay` of that stem.
3. Pass: `|AoAResult.azimuth_deg - 30| ≤ 2°` at high SNR (tighter than the 5° RMS field goal).

[test_aoa_theta30.py](test_aoa_theta30.py) is skipped until `aoa` is implemented. Do not implement MUSIC inside the test.

## Out of scope

- Hardware-in-the-loop in this skeleton.
- Asserting a valid `GeoFix` from one station.
