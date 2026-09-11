"""SDR live gates, --save IqFrame pair, and --replay without UHD."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import numpy as np
import pytest

from sdr.channel_map import ChannelMap, assert_live_allowed, channel_map_from_dict, load_channel_map
from sdr.cli import main as sdr_main
from sdr.errors import LiveRejected
from sdr.iqframe import HEADER_KEYS
from sdr.replay import load_replay, save_replay

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_STEM = ROOT / "tests" / "golden" / "theta30_m4"
CHANNEL_MAP = ROOT / "configs" / "channel_map.yaml"


def _scratch_dir() -> Path:
    d = ROOT / "tests" / "_scratch" / uuid.uuid4().hex
    d.mkdir(parents=True, exist_ok=True)
    return d


def test_import_sdr_does_not_import_uhd():
    code = (
        "import sys\n"
        "import sdr\n"
        "assert 'uhd' not in sys.modules, sorted(sys.modules)\n"
        "from sdr.replay import load_replay\n"
        "assert 'uhd' not in sys.modules\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


def test_replay_cli_does_not_import_uhd():
    code = (
        "import sys\n"
        "from sdr.cli import main\n"
        f"assert main(['--replay', r'{GOLDEN_STEM}']) == 0\n"
        "assert 'uhd' not in sys.modules\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


def test_save_writes_frozen_iqframe_pair():
    scratch = _scratch_dir()
    try:
        frame = load_replay(GOLDEN_STEM)
        stem = scratch / "cap"
        npy_path, meta_path = save_replay(stem, frame)
        assert npy_path.name == "cap.npy"
        assert meta_path.name == "cap.meta.json"

        header = json.loads(meta_path.read_text(encoding="utf-8"))
        assert "iq" not in header
        assert set(HEADER_KEYS) <= set(header)

        iq = np.load(npy_path, allow_pickle=False)
        assert iq.dtype == np.complex64
        assert iq.shape == (frame.n_chan, frame.n_samp)
        loaded = load_replay(stem)
        assert loaded.channel_ids == [0, 1, 2, 3]
        assert loaded.element_ids == [1, 3, 5, 7]
        np.testing.assert_array_equal(loaded.iq, frame.iq)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def test_sdr_replay_save_cli():
    scratch = _scratch_dir()
    stem = scratch / "copied"
    try:
        assert sdr_main(["--replay", str(GOLDEN_STEM), "--save", str(stem)]) == 0
        loaded = load_replay(stem)
        src = load_replay(GOLDEN_STEM)
        assert loaded.to_header()["n_chan"] == 4
        np.testing.assert_array_equal(loaded.iq, src.iq)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def test_live_refuses_unless_lo_share_true():
    raw = {
        "schema_version": 1,
        "M": 4,
        "lo_share": False,
        "replay_only": False,
        "device_args": "",
        "usrp_serial": "ABC",
        "mapping": [
            {
                "channel_index": 0,
                "element_id": 1,
                "usrp_chan": "A:0",
                "twinrx_slot": "A",
                "twinrx_rx": 0,
            },
            {
                "channel_index": 1,
                "element_id": 3,
                "usrp_chan": "A:1",
                "twinrx_slot": "A",
                "twinrx_rx": 1,
            },
            {
                "channel_index": 2,
                "element_id": 5,
                "usrp_chan": "B:0",
                "twinrx_slot": "B",
                "twinrx_rx": 0,
            },
            {
                "channel_index": 3,
                "element_id": 7,
                "usrp_chan": "B:1",
                "twinrx_slot": "B",
                "twinrx_rx": 1,
            },
        ],
    }
    cmap = channel_map_from_dict(raw)
    with pytest.raises(LiveRejected, match="lo_share"):
        assert_live_allowed(cmap)

    raw["lo_share"] = True
    assert_live_allowed(channel_map_from_dict(raw))


def test_live_cli_rejects_lo_share_false():
    scratch = _scratch_dir()
    cfg = scratch / "no_lo.yaml"
    try:
        cfg.write_text(
            Path(CHANNEL_MAP).read_text(encoding="utf-8").replace(
                "lo_share: true", "lo_share: false"
            ),
            encoding="utf-8",
        )
        assert sdr_main(["--live", "--config", str(cfg)]) == 2
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def test_channel_order_a0_to_1_through_b1_to_7():
    cmap = load_channel_map(CHANNEL_MAP)
    assert isinstance(cmap, ChannelMap)
    assert cmap.rx_subdev_spec() == "A:0 A:1 B:0 B:1"
    assert cmap.element_ids() == [1, 3, 5, 7]
    assert cmap.channel_ids() == [0, 1, 2, 3]
    ordered = cmap.ordered()
    assert [m.usrp_chan for m in ordered] == ["A:0", "A:1", "B:0", "B:1"]
    assert [m.element_id for m in ordered] == [1, 3, 5, 7]
