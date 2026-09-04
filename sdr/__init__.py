"""SDR acquisition and replay.

Produces IqFrame. ``import sdr`` and ``--replay`` do not import UHD.
Live capture is loaded only when opening a radio.
"""

from sdr.channel_map import ChannelMap, assert_live_allowed, load_channel_map
from sdr.errors import LiveRejected, ReplayError, SdrError
from sdr.iqframe import IqFrame, SCHEMA_VERSION
from sdr.replay import ReplaySource, load_replay, save_replay

__all__ = [
    "SCHEMA_VERSION",
    "ChannelMap",
    "IqFrame",
    "LiveRejected",
    "ReplayError",
    "ReplaySource",
    "SdrError",
    "assert_live_allowed",
    "load_channel_map",
    "load_replay",
    "save_replay",
]
