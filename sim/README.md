# sim

Synthetic array snapshots with a known arrival angle, written as npy + meta for `--replay`.

## Intended generator (not implemented in this skeleton)

For M=4, `phi_deg = [0, 90, 180, 270]`, placeholder `R_m` from `configs/array_uca_m4.yaml` once filled:

```text
x(n) = a(θ=30°) s(n) + noise
```

- SNR about 20 dB, N ≥ 1024 snapshots.
- `a(θ)` uses the UCA formula in [docs/interfaces.md](../docs/interfaces.md); `R_m` is the fixture radius, **not** HFSS “半径 xx mm” files under `阵列天线/优化结果/`.
- Write `tests/golden/theta30_m4.npy` and `tests/golden/theta30_m4.meta.json`.

## Out of scope

- MUSIC peak picking (that is `aoa/`).
- Live UHD.
