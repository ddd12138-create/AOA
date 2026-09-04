"""Load / write <stem>.npy + <stem>.meta.json (docs/interfaces.md file replay)."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import replace
from pathlib import Path

import numpy as np

from sdr.errors import ReplayError
from sdr.iqframe import IqFrame, frame_from_header_and_iq


def resolve_stem(stem: str | Path) -> Path:
    path = Path(stem)
    name = path.name
    if name.endswith(".meta.json"):
        return path.with_name(name[: -len(".meta.json")])
    if path.suffix == ".npy":
        return path.with_suffix("")
    return path


def replay_paths(stem: str | Path) -> tuple[Path, Path]:
    base = resolve_stem(stem)
    return base.with_suffix(".npy"), Path(str(base) + ".meta.json")


def load_replay(stem: str | Path) -> IqFrame:
    npy_path, meta_path = replay_paths(stem)
    if not npy_path.is_file():
        raise ReplayError(f"replay npy not found: {npy_path}")
    if not meta_path.is_file():
        raise ReplayError(f"replay meta.json not found: {meta_path}")

    try:
        header = json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReplayError(f"invalid meta JSON: {meta_path}") from exc
    if not isinstance(header, dict):
        raise ReplayError("meta.json must be a JSON object (IqFrame without iq)")
    if "iq" in header:
        raise ReplayError("meta.json must not embed iq")

    try:
        iq = np.load(npy_path, allow_pickle=False)
    except Exception as exc:
        raise ReplayError(f"failed to load npy: {npy_path}") from exc

    try:
        return frame_from_header_and_iq(header, iq)
    except Exception as exc:
        raise ReplayError(str(exc)) from exc


def save_replay(stem: str | Path, frame: IqFrame) -> tuple[Path, Path]:
    npy_path, meta_path = replay_paths(stem)
    npy_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(npy_path, np.ascontiguousarray(frame.iq, dtype=np.complex64))
    meta_path.write_text(
        json.dumps(frame.to_header(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return npy_path, meta_path


class ReplaySource:
    """Repeat the file frame. frame_id stays the value from meta.json."""

    def __init__(self, stem: str | Path) -> None:
        self.frame = load_replay(stem)
        self.fc_hz = self.frame.fc_hz
        self.fs_hz = self.frame.fs_hz
        self.gain_db: float | None = None
        self._period_s = _replay_period_s(self.frame.n_samp, self.fs_hz)
        self._next_t: float | None = None
        self._stop = threading.Event()

    def tune(
        self,
        *,
        fc_hz: float | None = None,
        fs_hz: float | None = None,
        gain_db: float | None = None,
    ) -> None:
        if fc_hz is not None:
            self.fc_hz = float(fc_hz)
        if fs_hz is not None:
            self.fs_hz = float(fs_hz)
            self._period_s = _replay_period_s(self.frame.n_samp, self.fs_hz)
        if gain_db is not None:
            self.gain_db = float(gain_db)

    def start(self) -> None:
        self._stop.clear()
        self._next_t = None

    def stop(self) -> None:
        self._stop.set()
        self._next_t = None

    def close(self) -> None:
        self.stop()

    def next_frame(self) -> IqFrame:
        now = time.monotonic()
        if self._next_t is None:
            self._next_t = now
        delay = self._next_t - now
        if delay > 0:
            self._stop.wait(delay)
        if not self._stop.is_set():
            self._next_t += self._period_s
        return replace(self.frame, fc_hz=self.fc_hz, fs_hz=self.fs_hz)


def _replay_period_s(n_samp: int, fs_hz: float) -> float:
    if fs_hz and fs_hz > 0:
        return max(float(n_samp) / float(fs_hz), 1e-3)
    return 0.05
