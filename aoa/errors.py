"""AOA errors. Missing radius must abort azimuth, never invent R_m."""


class MissingArrayRadiusError(ValueError):
    """ArrayGeometry.R_m is null or non-positive; refuse to emit azimuth.

    Do not fall back to HFSS '半径 xx mm' plots or any guessed jig radius.
    """
