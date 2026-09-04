# detect

Spectrum scout and burst detector. Consumes `IqFrame`, produces `DetectionEvent`.

## Scope

- Energy scan on 900 MHz / 2.4 GHz / 5.8 GHz (see `configs/bands.yaml`).
- Burst start/stop in sample index and UTC ns, plus `iq_ref` into the parent frame.
- SNR in dB.

## Out of scope

- MUSIC, UHD, Qt, lat/lon.
- Changing `IqFrame` / `DetectionEvent` field names (those live in [docs/interfaces.md](../docs/interfaces.md)).
