# calib

Amplitude/phase calibration files consumed by `aoa` through `ArrayGeometry.calib_path`.

## Files

- [identity.yaml](identity.yaml) — unity gain, zero extra phase, M=4. Use only when uncalibrated; host/worker must label the run `uncalibrated`.

## When to re-calibrate

See [docs/runbook.md](../docs/runbook.md): after cable swap, temperature swing, site move, or `channel_map.yaml` change.

## Format (frozen with interfaces)

See `CalibFile` in [docs/interfaces.md](../docs/interfaces.md). Coefficients apply per `channel_ids` row of `a(θ)`, not by TwinRX port name alone.

## Out of scope

- Measuring calib from a splitter or chamber in this skeleton.
- Copying HFSS element phase-center offsets into `R_m`.
