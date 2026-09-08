# calib

Amplitude/phase calibration files consumed by `aoa` through `ArrayGeometry.calib_path`.

## Files

- [identity.yaml](identity.yaml) — unity gain, zero extra phase, M=4. Use only when uncalibrated; host/worker must label the run `uncalibrated`. Do not overwrite this file; it is not a chamber result.

## Known-source CLI (narrowband)

Replay an IqFrame, cut a `detect` burst, and estimate each channel's `gain_lin` / `phase_rad` relative to channel 0 at a known array-frame azimuth. Requires `ArrayGeometry.R_m` in metres (simulation: `configs/array_uca_m4_sim.yaml`). Refuses when `R_m` is null — never guess a jig or HFSS millimetre radius.

```text
python -m calib --replay tests/golden/theta30_m4 --theta-deg 30 --array configs/array_uca_m4_sim.yaml --out calib/sim_theta30.yaml
```

Then point `ArrayGeometry.calib_path` at the new YAML (repo-root relative). Output fields match `CalibFile` in [docs/interfaces.md](../docs/interfaces.md): `schema_version=1`, `status=calibrated`, `fc_hz` from the frame.

## When to re-calibrate

See [docs/runbook.md](../docs/runbook.md): after cable swap, temperature swing, site move, or `channel_map.yaml` change.

## Format (frozen with interfaces)

See `CalibFile` in [docs/interfaces.md](../docs/interfaces.md). Coefficients apply per `channel_ids` row of `a(θ)`, not by TwinRX port name alone.

## Out of scope

- X310 live capture (use `--replay` only).
- Multi-station geolocation.
- Copying HFSS element phase-center offsets into `R_m`.
