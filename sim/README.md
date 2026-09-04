# sim

Synthetic array snapshots with a known arrival angle, written as npy + meta for `--replay`.

## Generator

```text
python -m sim
```

Uses `configs/array_uca_m4_sim.yaml` (`R_m: 0.15`, header: **simulation only, not fixture**).

```text
x(n) = a(θ=30°) s(n) + noise
```

- SNR about 20 dB, N = 2048 snapshots, M=4, `phi_deg = [0, 90, 180, 270]`.
- `a(θ)` is the UCA formula in [docs/interfaces.md](../docs/interfaces.md).
- Writes `tests/golden/theta30_m4.npy` and `tests/golden/theta30_m4.meta.json`.

Do not copy the simulation `R_m` onto `configs/array_uca_m4.yaml` (hardware jig stays `null` until measured). Not HFSS “半径 xx mm”.

## Out of scope

- MUSIC peak picking (that is `aoa/`).
- Live UHD.
