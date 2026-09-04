# geo

Reserved multi-station intersection / GeoFix. Single-station AOA is azimuth only.

## Scope

- Keep `GeoFix.valid = false` for the current one-station system.
- Future: two or more stations, WGS84 site positions, ENU intersection. Interface already frozen in [docs/interfaces.md](../docs/interfaces.md).

## Out of scope

- Drawing a pilot (flyer) lat/lon from one station’s `azimuth_deg`.
- RSS / range-to-position hacks presented as a GeoFix in the M=4 host UI.
