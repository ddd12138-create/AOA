"""Skip until aoa MUSIC exists. Do not implement peak search in this test."""

import pytest

pytestmark = pytest.mark.skip(reason="aoa not implemented")


def test_aoa_theta30_within_two_degrees():
    """Replay tests/golden/theta30_m4; expect |azimuth_deg - 30| <= 2.

    Golden files are produced later by sim/. This is algorithm regression,
    not the field 5° RMS spec. Do not call MUSIC from the test body.
    """
    golden_stem = "tests/golden/theta30_m4"
    _ = golden_stem
    raise AssertionError("aoa not implemented")
