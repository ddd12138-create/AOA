"""Read/write CalibFile YAML. identity.yaml is a reserved uncalibrated placeholder."""

from __future__ import annotations

from pathlib import Path

from aoa.constants import SCHEMA_VERSION
from aoa.geometry import CalibFile, load_calib_file

from calib.errors import CalibError

IDENTITY_NAME = "identity.yaml"
IDENTITY_RELPATH = "calib/identity.yaml"


def is_identity_path(path: str | Path) -> bool:
    return Path(path).name == IDENTITY_NAME


def dump_calib_yaml(calib: CalibFile) -> str:
    if calib.schema_version != SCHEMA_VERSION:
        raise CalibError(f"schema_version must be {SCHEMA_VERSION}")
    if calib.status != "calibrated":
        raise CalibError('this writer only emits status=calibrated')
    fc = "null" if calib.fc_hz is None else repr(float(calib.fc_hz))
    return (
        "# Narrowband known-source channel calib (relative to channel 0).\n"
        "# Do not replace calib/identity.yaml; identity remains uncalibrated.\n"
        f"schema_version: {int(calib.schema_version)}\n"
        f"M: {int(calib.M)}\n"
        f"channel_ids: {_flow_ints(calib.channel_ids)}\n"
        f"gain_lin: {_flow_floats(calib.gain_lin)}\n"
        f"phase_rad: {_flow_floats(calib.phase_rad)}\n"
        f"status: {calib.status}\n"
        f"fc_hz: {fc}\n"
    )


def write_calib_file(path: str | Path, calib: CalibFile) -> Path:
    out = Path(path)
    if is_identity_path(out):
        raise CalibError(
            f"refusing to overwrite {IDENTITY_RELPATH}; write a new file such as "
            "calib/sim_theta30.yaml and point ArrayGeometry.calib_path at it"
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(dump_calib_yaml(calib), encoding="utf-8")
    return out


def _flow_ints(values: object) -> str:
    return "[" + ", ".join(str(int(x)) for x in values) + "]"


def _flow_floats(values: object) -> str:
    return "[" + ", ".join(_fmt_float(float(x)) for x in values) + "]"


def _fmt_float(value: float) -> str:
    text = f"{value:.12g}"
    if "." not in text and "e" not in text and "E" not in text:
        text += ".0"
    return text


__all__ = [
    "IDENTITY_NAME",
    "IDENTITY_RELPATH",
    "dump_calib_yaml",
    "is_identity_path",
    "load_calib_file",
    "write_calib_file",
]
