"""SDR errors. LiveRejected is raised before any UHD import when live is illegal."""


class SdrError(Exception):
    """Base error for acquisition and replay."""


class ReplayError(SdrError):
    """npy / meta.json pair is missing or does not match IqFrame."""


class LiveRejected(SdrError):
    """--live refused (LO share, channel count, or mapping)."""


class RxOverflow(SdrError):
    """UHD dropped samples. Discard this frame and keep streaming."""
