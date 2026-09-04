"""Physical and search-grid constants for UCA MUSIC."""

# SI speed of light (m/s). λ = c / fc_hz.
C_MPS = 299792458.0

SCHEMA_VERSION = 1
DEFAULT_M = 4
GRID_START_DEG = 0.0
GRID_STOP_DEG = 360.0  # exclusive, matches music_spectrum_summary
GRID_STEP_DEG = 0.5
# M=4 stage: do not claim K >= 3.
K_MAX_M4 = 2
