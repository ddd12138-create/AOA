# aoa

MUSIC angle-of-arrival estimator. Consumes `DetectionEvent` + referenced IQ, produces `AoAResult`.

## Scope

- Steering vector `a(θ)` from `ArrayGeometry` (`R_m`, `phi_deg`, `λ = c/fc_hz`) and calib coefficients.
- `M` is variable; default **M=4**. Do not hard-code 8.
- Output azimuth in the array frame (`azimuth_deg`). `elevation_deg` is `null` in the M=4 phase.
- Single-station results attach an **invalid** `GeoFix` (`valid=false`). Never fill lat/lon here.
- `R_m is null` raises `MissingArrayRadiusError` — no guessed radius, no HFSS millimetres.
- Identity calib (`calib/identity.yaml`) keeps `uncalibrated=true` on the worker `status` fields, not inside `AoAResult`.

## Out of scope

- Qt widgets, UHD, multi-station GeoFix.
- Treating HFSS “半径 xx mm” optimization plots as UCA radius `R_m`.

## Acceptance

`tests/test_aoa_theta30.py` expects `azimuth_deg` within 30° ± 2° on `tests/golden/theta30_m4` with `configs/array_uca_m4_sim.yaml`.
