# aoa

MUSIC angle-of-arrival estimator. Consumes `DetectionEvent` + referenced IQ, produces `AoAResult`.

## Scope

- Steering vector `a(θ)` from `ArrayGeometry` (`R_m`, `phi_deg`, `λ = c/fc_hz`) and calib coefficients.
- `M` is variable; default **M=4**. Do not hard-code 8.
- Output azimuth in the array frame (`azimuth_deg`). `elevation_deg` is optional and `null` in the M=4 phase.
- Single-station results must attach an **invalid** `GeoFix` (or omit it). Never fill lat/lon here.

## Out of scope

- Qt widgets, UHD, multi-station GeoFix.
- Treating HFSS “半径 xx mm” optimization plots as UCA radius `R_m`.
- Implementing MUSIC in the documentation-skeleton phase.

## Acceptance (later)

`tests/test_aoa_theta30.py` expects `azimuth_deg` within 30° ± 2° on the golden replay. That test is skipped until this package exists.
