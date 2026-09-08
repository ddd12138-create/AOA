"""Errors raised by detect. Not used for 'no signal' (that is an empty list)."""


class DetectError(ValueError):
    """Invalid IqFrame or band config. Absence of a burst is not an error."""
