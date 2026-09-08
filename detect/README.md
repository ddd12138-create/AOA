# detect

Spectrum scout and burst detector. Consumes `IqFrame`, produces `DetectionEvent`.

## Scope

- Narrowband energy scan on 900 MHz / 2.4 GHz / 5.8 GHz (`configs/bands.yaml`).
- Tune frequencies outside those windows yield no event (not a band guess).
- Burst start/stop in sample index and UTC ns, plus `iq_ref` into the parent frame.
- SNR in dB. No IQ copy on the event.

`detect_frame(frame, first_event_id=1)` returns `[]` when the snapshot is idle.
That is not an error: worker must not go to `status.state=error` for silence.

## Out of scope

- MUSIC, UHD, Qt, lat/lon, protocol decode / hopping dwell.
- Changing `IqFrame` / `DetectionEvent` field names (those live in [docs/interfaces.md](../docs/interfaces.md)).
