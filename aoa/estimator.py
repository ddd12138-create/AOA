"""MUSIC azimuth estimator. M variable, default 4. No Qt, no UHD, no GeoFix."""

from __future__ import annotations

from pathlib import Path

from aoa.constants import (
    DEFAULT_M,
    GRID_START_DEG,
    GRID_STEP_DEG,
    GRID_STOP_DEG,
    SCHEMA_VERSION,
)
from aoa.geometry import (
    ArrayGeometry,
    CalibFile,
    load_array_geometry,
    load_calib_file,
    require_radius_m,
    resolve_calib_path,
    steering_matrix,
)
from aoa.music import (
    azimuth_grid_deg,
    confidence_from_spectrum,
    eig_sorted,
    estimate_k,
    music_power,
    sample_covariance,
    spectrum_summary,
)
from aoa.types import AoAOutput, AoAResult, DetectionEvent, IqFrame, invalid_geo_fix


class MusicEstimator:
    """Single-station UCA MUSIC. elevation_deg is always null; geo_fix.valid is false."""

    def __init__(self, geometry: ArrayGeometry, calib: CalibFile) -> None:
        if geometry.M != calib.M:
            raise ValueError("ArrayGeometry.M must match CalibFile.M")
        self.geometry = geometry
        self.calib = calib
        self._result_id = 0

    @classmethod
    def from_array_yaml(
        cls,
        array_yaml: str | Path,
        repo_root: str | Path,
        calib_path: str | Path | None = None,
    ) -> MusicEstimator:
        geometry = load_array_geometry(array_yaml)
        calib_file = Path(calib_path) if calib_path is not None else resolve_calib_path(
            geometry, repo_root
        )
        calib = load_calib_file(calib_file)
        return cls(geometry, calib)

    @property
    def uncalibrated(self) -> bool:
        return self.calib.uncalibrated

    @property
    def M(self) -> int:
        return int(self.geometry.M)

    def estimate(self, frame: IqFrame, event: DetectionEvent) -> AoAOutput:
        require_radius_m(self.geometry)
        if frame.n_chan != self.geometry.M:
            raise ValueError("IqFrame.n_chan must match ArrayGeometry.M")
        if list(frame.element_ids) != list(self.geometry.element_ids):
            raise ValueError("IqFrame.element_ids must match ArrayGeometry.element_ids")

        start = int(event.iq_ref.start_samp)
        end = int(event.iq_ref.end_samp)
        if start < 0 or end > frame.n_samp or end <= start:
            raise ValueError("iq_ref sample range is empty or out of bounds")
        iq = frame.iq[:, start:end]
        m, n = iq.shape
        if m != self.geometry.M:
            raise ValueError("IQ channel count does not match M")
        if n < self.geometry.M:
            raise ValueError("need at least M snapshots")

        thetas = azimuth_grid_deg(GRID_START_DEG, GRID_STOP_DEG, GRID_STEP_DEG)
        a_theta = steering_matrix(thetas, self.geometry, frame.fc_hz, self.calib)
        rxx = sample_covariance(iq)
        eigvals, eigvecs = eig_sorted(rxx)
        k_est = estimate_k(eigvals, n, m, detected=True)
        noise = eigvecs[:, k_est:]
        power = music_power(a_theta, noise)
        summary = spectrum_summary(
            thetas,
            power,
            grid_start_deg=GRID_START_DEG,
            grid_stop_deg=GRID_STOP_DEG,
            grid_step_deg=GRID_STEP_DEG,
        )
        if summary.n_peaks < 1:
            raise RuntimeError("MUSIC spectrum has no peaks")
        azimuth = float(summary.peaks[0].theta_deg) % 360.0
        confidence = confidence_from_spectrum(power)

        self._result_id += 1
        result = AoAResult(
            schema_version=SCHEMA_VERSION,
            result_id=self._result_id,
            timestamp_utc_ns=int(event.timestamp_utc_ns),
            detection_event_id=int(event.event_id),
            azimuth_deg=azimuth,
            elevation_deg=None,
            confidence=confidence,
            music_spectrum_summary=summary,
            M=int(self.geometry.M if self.geometry.M else DEFAULT_M),
            element_ids=[int(x) for x in frame.element_ids],
            K_est=int(k_est),
            geo_fix=invalid_geo_fix(),
        )
        return AoAOutput(
            result=result,
            uncalibrated=self.uncalibrated,
            calib_status=self.calib.status,
        )
