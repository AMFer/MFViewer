"""
Engine model for VE (Volumetric Efficiency) prediction and extrapolation.

This module implements an alpha-N style engine model that predicts VE based on
RPM and throttle position. The model can be fitted to measured data and used
to extrapolate VE values to unmeasured regions of the map.

Model Theory:
- VE peaks at torque peak RPM (typically 60-80% of redline)
- VE follows torque curve shape
- Throttle response is non-linear (butterfly valve)
- Model: VE(rpm, tps) = VE_base × rpm_factor(rpm) × tps_factor(tps)
"""

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

# Try to import scipy for curve fitting
try:
    from scipy.optimize import curve_fit, least_squares
    from scipy.stats import pearsonr
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False


@dataclass
class EngineConfig:
    """Saveable engine configuration for VE model."""

    name: str = "New Engine"
    displacement_cc: float = 2000.0
    peak_torque_rpm: float = 4500.0
    redline_rpm: float = 7000.0
    valve_config: str = "4V"  # "2V" or "4V"
    cam_profile: str = "stock"  # "stock", "mild", "aggressive"
    peak_ve_estimate: float = 95.0  # Expected max VE%

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'EngineConfig':
        """Create from dictionary."""
        return cls(**data)

    def get_cam_width_factor(self) -> float:
        """Get RPM curve width factor based on cam profile.

        Aggressive cams have wider, shifted power bands.
        """
        factors = {
            "stock": 0.25,
            "mild": 0.35,
            "aggressive": 0.45
        }
        return factors.get(self.cam_profile, 0.30)

    def get_default_peak_ve(self) -> float:
        """Get default peak VE based on valve configuration."""
        defaults = {
            "2V": 88.0,
            "4V": 98.0
        }
        return defaults.get(self.valve_config, 90.0)


@dataclass
class FitStatistics:
    """Model fit quality metrics."""

    r_squared: float = 0.0
    rmse: float = 0.0
    max_error: float = 0.0
    mean_error: float = 0.0
    n_points: int = 0
    residuals: np.ndarray = field(default_factory=lambda: np.array([]))
    cell_errors: Optional[np.ndarray] = None  # Same shape as VE map

    def to_dict(self) -> Dict:
        """Convert to dictionary (without numpy arrays)."""
        return {
            'r_squared': self.r_squared,
            'rmse': self.rmse,
            'max_error': self.max_error,
            'mean_error': self.mean_error,
            'n_points': self.n_points
        }


class AlphaNModel:
    """Alpha-N VE model for naturally aspirated engines.

    This model can operate in two modes:
    1. Absolute VE prediction: VE(rpm, tps) = VE_base × rpm_factor(rpm) × tps_factor(tps)
    2. Correction ratio interpolation: Uses measured corrections and interpolates to unmeasured cells

    The correction ratio mode is more practical for test stand data where we have
    lambda measurements at various operating points but not at WOT under load.
    """

    def __init__(self, config: EngineConfig):
        """Initialize the model with engine configuration.

        Args:
            config: Engine configuration parameters
        """
        self.config = config
        self.fitted_params: Optional[Dict] = None
        self.fit_stats: Optional[FitStatistics] = None

        # Default model parameters (will be updated by fitting)
        self._ve_base = config.peak_ve_estimate
        self._rpm_sigma = (config.redline_rpm - config.peak_torque_rpm) * config.get_cam_width_factor()
        self._rpm_min_factor = 0.3  # VE factor at 0 RPM (ramps up linearly to 1.0 at peak torque)

        # TPS model parameters for butterfly valve cosine model
        # Airflow through a butterfly valve follows: A ∝ (1 - cos(θ))
        # where θ is the throttle plate angle (0° = closed, 90° = fully open)
        # TPS% maps to angle: θ = TPS/100 * π/2
        # We add a minimum idle flow and allow fitting to adjust the curve shape
        self._tps_idle_flow = 0.02  # Minimum flow at closed throttle (2%)
        self._tps_exponent = 1.0    # Exponent to adjust curve shape (fittable)

        # For correction ratio interpolation mode
        self._correction_ratios: Optional[np.ndarray] = None  # Measured correction ratios
        self._correction_rpm: Optional[np.ndarray] = None     # RPM values for corrections
        self._correction_tps: Optional[np.ndarray] = None     # TPS values for corrections
        self._avg_correction: float = 1.0                     # Average correction for fallback

    def rpm_factor(self, rpm: np.ndarray) -> np.ndarray:
        """Calculate RPM-based VE factor.

        Uses a piecewise model:
        - Below peak torque: linear increase from min_rpm_factor to 1.0
        - Above peak torque: gradual linear decay to redline_decay_factor at redline

        This better represents real engine behavior where VE rises with RPM
        up to the torque peak (better volumetric pumping, tuned intake/exhaust),
        then falls off gradually at high RPM (flow restrictions, valve timing issues).

        Args:
            rpm: RPM value(s)

        Returns:
            Normalized factor (peaks at 1.0 at peak torque RPM)
        """
        peak_rpm = self.config.peak_torque_rpm
        redline = self.config.redline_rpm

        # Minimum RPM factor at very low RPM (idle)
        min_rpm_factor = self._rpm_min_factor

        # Factor at redline - typically 85-95% of peak for high-performance engines
        # Use cam profile to determine how much VE falls off at redline
        redline_decay = {
            "stock": 0.80,       # Stock cams lose more VE at high RPM
            "mild": 0.85,        # Mild cams hold VE better
            "aggressive": 0.90   # Aggressive cams designed for high RPM
        }
        redline_factor = redline_decay.get(self.config.cam_profile, 0.85)

        # Convert to numpy array if scalar
        rpm = np.atleast_1d(rpm)
        factor = np.ones_like(rpm, dtype=np.float64)

        # Below peak torque: linear ramp from min_factor at 0 RPM to 1.0 at peak
        below_peak = rpm < peak_rpm
        factor[below_peak] = min_rpm_factor + (1.0 - min_rpm_factor) * (rpm[below_peak] / peak_rpm)

        # Above peak torque: linear decay from 1.0 to redline_factor at redline
        # Continue decaying linearly beyond redline
        above_peak = rpm >= peak_rpm
        rpm_above = rpm[above_peak]
        decay_slope = (1.0 - redline_factor) / (redline - peak_rpm)
        factor[above_peak] = 1.0 - decay_slope * (rpm_above - peak_rpm)

        # Clamp to minimum (can't be negative)
        factor = np.maximum(factor, 0.05)

        return factor

    def tps_factor(self, tps: np.ndarray) -> np.ndarray:
        """Calculate TPS-based VE factor using butterfly valve physics.

        Butterfly valve effective area follows: A ∝ (1 - cos(θ))
        where θ is the throttle plate angle from closed (0°) to fully open (90°).

        TPS% (0-100) maps to angle θ = TPS/100 * π/2

        The formula produces:
        - 0% TPS: 1 - cos(0) = 0 (closed)
        - 50% TPS: 1 - cos(π/4) ≈ 0.29 (29% flow)
        - 100% TPS: 1 - cos(π/2) = 1 (full flow)

        Args:
            tps: Throttle position (0-100%)

        Returns:
            Normalized factor (idle_flow at closed, 1.0 at WOT)
        """
        # Convert TPS% to angle in radians (0-100% -> 0 to π/2)
        theta = (tps / 100.0) * (np.pi / 2.0)

        # Butterfly valve area: 1 - cos(θ)
        # Apply exponent to allow curve shape adjustment
        raw_factor = 1.0 - np.cos(theta)

        # Apply exponent for curve shape tuning (default 1.0 = pure cosine model)
        if self._tps_exponent != 1.0:
            raw_factor = np.power(raw_factor, self._tps_exponent)

        # Add minimum idle flow and scale so max is 1.0
        # idle_flow + (1 - idle_flow) * raw_factor
        factor = self._tps_idle_flow + (1.0 - self._tps_idle_flow) * raw_factor

        # Clamp to valid range
        factor = np.clip(factor, 0.0, 1.0)

        return factor

    def predict(self, rpm: float, tps: float) -> float:
        """Predict VE for a single RPM/TPS point.

        Args:
            rpm: Engine RPM
            tps: Throttle position (0-100%)

        Returns:
            Predicted VE percentage
        """
        rpm_arr = np.array([rpm])
        tps_arr = np.array([tps])

        ve = self._ve_base * self.rpm_factor(rpm_arr) * self.tps_factor(tps_arr)
        return float(ve[0])

    def predict_array(self, rpm: np.ndarray, tps: np.ndarray) -> np.ndarray:
        """Predict VE for arrays of RPM/TPS values.

        Args:
            rpm: Array of RPM values
            tps: Array of TPS values (same length as rpm)

        Returns:
            Array of predicted VE percentages
        """
        return self._ve_base * self.rpm_factor(rpm) * self.tps_factor(tps)

    def predict_grid(self, rpm_axis: List[float],
                     tps_axis: List[float]) -> np.ndarray:
        """Predict VE for entire map grid.

        Args:
            rpm_axis: RPM breakpoints (columns)
            tps_axis: TPS/Load breakpoints (rows, typically descending)

        Returns:
            2D array of predicted VE values (shape: len(tps_axis) x len(rpm_axis))
        """
        # Create meshgrid
        rpm_grid, tps_grid = np.meshgrid(rpm_axis, tps_axis)

        # Predict for all points
        ve_grid = self._ve_base * self.rpm_factor(rpm_grid) * self.tps_factor(tps_grid)

        return ve_grid

    def fit(self, rpm_values: np.ndarray, tps_values: np.ndarray,
            ve_values: np.ndarray, weights: Optional[np.ndarray] = None) -> FitStatistics:
        """Fit model to measured VE data with peak VE constraint.

        The model is constrained so that at peak_torque_rpm and 100% TPS,
        the predicted VE equals the engine config's peak_ve_estimate.
        This allows fitting to low-TPS test stand data while still
        extrapolating correctly to WOT conditions.

        Args:
            rpm_values: RPM for each measured cell
            tps_values: TPS% for each measured cell
            ve_values: Measured VE% for each cell
            weights: Optional hit count (confidence) for each cell

        Returns:
            FitStatistics with R², residuals, per-cell errors
        """
        if not SCIPY_AVAILABLE:
            # Fall back to simple fitting without scipy
            return self._fit_simple(rpm_values, tps_values, ve_values, weights)

        if len(rpm_values) < 3:
            # Not enough data to fit
            return FitStatistics(n_points=len(rpm_values))

        if weights is None:
            weights = np.ones_like(rpm_values)

        # Normalize weights by hit count
        weights = weights / np.max(weights)

        # For test stand data (idle, no load), high-TPS readings are unreliable
        # because the engine isn't actually producing WOT power - it's just idle
        # with the throttle open. We should only fit to data where TPS < 60%,
        # which is more representative of actual engine behavior during testing.
        # The model will use the peak_ve_estimate to anchor WOT predictions.
        low_tps_mask = tps_values < 60.0

        if np.any(low_tps_mask) and np.sum(low_tps_mask) >= 5:
            # Filter to only low-TPS data for fitting
            rpm_values = rpm_values[low_tps_mask]
            tps_values = tps_values[low_tps_mask]
            ve_values = ve_values[low_tps_mask]
            weights = weights[low_tps_mask]

        # Target peak VE from config - this is what we want at peak_torque_rpm, 100% TPS
        target_peak_ve = self.config.peak_ve_estimate

        # Calculate the TPS factor at 100% TPS for the constrained model
        # At 100% TPS: theta = pi/2, raw_factor = 1 - cos(pi/2) = 1.0
        # So tps_factor = idle_flow + (1 - idle_flow) * 1^exponent = 1.0
        # This means at 100% TPS, rpm_factor = 1.0 (at peak RPM), VE = ve_base
        # So ve_base should equal target_peak_ve

        # Define the combined model function for curve_fit
        # Uses piecewise RPM model and cosine-based butterfly valve TPS model
        # ve_base is FIXED to target_peak_ve - we only fit the shape parameters
        def model_func(X, rpm_min_factor, tps_idle_flow, tps_exponent):
            rpm, tps = X
            peak_rpm = self.config.peak_torque_rpm
            redline = self.config.redline_rpm

            # Redline decay factor based on cam profile
            redline_decay = {
                "stock": 0.80,
                "mild": 0.85,
                "aggressive": 0.90
            }
            redline_factor = redline_decay.get(self.config.cam_profile, 0.85)

            # RPM factor - piecewise model:
            # Below peak: linear ramp from rpm_min_factor at 0 to 1.0 at peak
            # Above peak: linear decay to redline_factor at redline
            rpm_factor = np.ones_like(rpm, dtype=np.float64)
            below_peak = rpm < peak_rpm
            above_peak = ~below_peak

            rpm_factor[below_peak] = rpm_min_factor + (1.0 - rpm_min_factor) * (rpm[below_peak] / peak_rpm)

            # Linear decay above peak torque
            decay_slope = (1.0 - redline_factor) / (redline - peak_rpm)
            rpm_factor[above_peak] = 1.0 - decay_slope * (rpm[above_peak] - peak_rpm)
            rpm_factor = np.maximum(rpm_factor, 0.05)

            # TPS factor - Butterfly valve cosine model
            # θ = TPS/100 * π/2 (0% -> 0°, 100% -> 90°)
            theta = (tps / 100.0) * (np.pi / 2.0)
            raw_factor = 1.0 - np.cos(theta)

            # Apply exponent for curve shape tuning
            if tps_exponent != 1.0:
                raw_factor = np.power(np.clip(raw_factor, 1e-10, None), tps_exponent)

            # Add idle flow and scale
            tps_factor = tps_idle_flow + (1.0 - tps_idle_flow) * raw_factor
            tps_factor = np.clip(tps_factor, 0.0, 1.0)

            return target_peak_ve * rpm_factor * tps_factor

        # Initial parameter guesses (ve_base is fixed, so only 3 params now)
        p0 = [
            self._rpm_min_factor,
            self._tps_idle_flow,
            self._tps_exponent
        ]

        # Parameter bounds
        # idle_flow should be low (0-15%) - this is the minimum airflow at closed throttle
        # exponent adjusts the TPS curve shape
        bounds = (
            [0.1, 0.0, 0.3],         # Lower bounds: rpm_min_factor, idle_flow, exponent
            [0.8, 0.15, 3.0]         # Upper bounds - limit idle_flow to 15%
        )

        try:
            # Fit the model
            X_data = np.vstack([rpm_values, tps_values])

            popt, pcov = curve_fit(
                model_func, X_data, ve_values,
                p0=p0, bounds=bounds, sigma=1.0/weights, absolute_sigma=False,
                maxfev=5000
            )

            # Store fitted parameters - ve_base is fixed to target
            self._ve_base = target_peak_ve
            self._rpm_min_factor = popt[0]
            self._tps_idle_flow = popt[1]
            self._tps_exponent = popt[2]

            self.fitted_params = {
                've_base': target_peak_ve,
                'rpm_min_factor': popt[0],
                'tps_idle_flow': popt[1],
                'tps_exponent': popt[2]
            }

            # Calculate fit statistics
            predicted = model_func(X_data, *popt)
            residuals = ve_values - predicted

            # R-squared
            ss_res = np.sum(residuals**2)
            ss_tot = np.sum((ve_values - np.mean(ve_values))**2)
            r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

            # RMSE
            rmse = np.sqrt(np.mean(residuals**2))

            # Max and mean error
            max_error = np.max(np.abs(residuals))
            mean_error = np.mean(np.abs(residuals))

            self.fit_stats = FitStatistics(
                r_squared=r_squared,
                rmse=rmse,
                max_error=max_error,
                mean_error=mean_error,
                n_points=len(rpm_values),
                residuals=residuals
            )

            return self.fit_stats

        except Exception as e:
            # Fitting failed, return empty stats
            print(f"Model fitting failed: {e}")
            return FitStatistics(n_points=len(rpm_values))

    def _fit_simple(self, rpm_values: np.ndarray, tps_values: np.ndarray,
                    ve_values: np.ndarray, weights: Optional[np.ndarray] = None) -> FitStatistics:
        """Simple fitting without scipy (fallback).

        Uses the peak_ve_estimate from config as ve_base (constrained).
        """
        if len(rpm_values) == 0:
            return FitStatistics()

        # Use the peak VE estimate from config (constrained approach)
        self._ve_base = self.config.peak_ve_estimate

        self.fitted_params = {
            've_base': self._ve_base,
            'rpm_min_factor': self._rpm_min_factor,
            'tps_idle_flow': self._tps_idle_flow,
            'tps_exponent': self._tps_exponent
        }

        # Calculate residuals
        predicted = self.predict_array(rpm_values, tps_values)
        residuals = ve_values - predicted

        # Statistics
        ss_res = np.sum(residuals**2)
        ss_tot = np.sum((ve_values - np.mean(ve_values))**2)
        r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

        rmse = np.sqrt(np.mean(residuals**2))
        max_error = np.max(np.abs(residuals))
        mean_error = np.mean(np.abs(residuals))

        self.fit_stats = FitStatistics(
            r_squared=r_squared,
            rmse=rmse,
            max_error=max_error,
            mean_error=mean_error,
            n_points=len(rpm_values),
            residuals=residuals
        )

        return self.fit_stats

    def fit_corrections(self, rpm_values: np.ndarray, tps_values: np.ndarray,
                        base_ve_values: np.ndarray, corrected_ve_values: np.ndarray,
                        weights: Optional[np.ndarray] = None) -> FitStatistics:
        """Fit a correction ratio model for interpolation.

        Instead of fitting an absolute VE model, this stores correction ratios
        (corrected_ve / base_ve) at measured points and provides interpolation
        for unmeasured cells. This is more robust for test stand data.

        Args:
            rpm_values: RPM for each measured cell
            tps_values: TPS% for each measured cell
            base_ve_values: Base VE from the map for each cell
            corrected_ve_values: Lambda-corrected VE for each cell
            weights: Optional hit count for weighting

        Returns:
            FitStatistics with correction ratio statistics
        """
        if len(rpm_values) == 0:
            return FitStatistics()

        # Calculate correction ratios
        valid_mask = base_ve_values > 0
        correction_ratios = np.ones_like(base_ve_values)
        correction_ratios[valid_mask] = corrected_ve_values[valid_mask] / base_ve_values[valid_mask]

        # Store for interpolation
        self._correction_rpm = rpm_values.copy()
        self._correction_tps = tps_values.copy()
        self._correction_ratios = correction_ratios.copy()

        # Calculate weighted average correction
        if weights is not None:
            self._avg_correction = np.average(correction_ratios, weights=weights)
        else:
            self._avg_correction = np.mean(correction_ratios)

        # Store as fitted params for display
        self.fitted_params = {
            'avg_correction': self._avg_correction,
            'min_correction': float(np.min(correction_ratios)),
            'max_correction': float(np.max(correction_ratios)),
            'n_points': len(rpm_values)
        }

        # Calculate statistics on the correction ratios
        residuals = correction_ratios - self._avg_correction
        ss_res = np.sum(residuals**2)
        ss_tot = np.sum((correction_ratios - np.mean(correction_ratios))**2)
        r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

        # For corrections, use ratio units in stats
        rmse = np.sqrt(np.mean(residuals**2))
        max_error = np.max(np.abs(residuals))
        mean_error = np.mean(np.abs(residuals))

        self.fit_stats = FitStatistics(
            r_squared=r_squared,
            rmse=rmse * 100,  # Convert to percentage points
            max_error=max_error * 100,
            mean_error=mean_error * 100,
            n_points=len(rpm_values),
            residuals=residuals
        )

        return self.fit_stats

    def predict_correction(self, rpm: float, tps: float) -> float:
        """Predict correction ratio for a cell using inverse distance weighting.

        Args:
            rpm: Engine RPM
            tps: Throttle position (0-100%)

        Returns:
            Predicted correction ratio (multiply by base VE to get corrected VE)
        """
        if self._correction_ratios is None or len(self._correction_ratios) == 0:
            return self._avg_correction

        # Normalize coordinates for distance calculation
        # RPM range is 0-10000, TPS is 0-100, scale to similar magnitudes
        rpm_scale = 100.0
        tps_scale = 1.0

        rpm_norm = rpm / rpm_scale
        tps_norm = tps / tps_scale

        ref_rpm_norm = self._correction_rpm / rpm_scale
        ref_tps_norm = self._correction_tps / tps_scale

        # Calculate distances to all reference points
        distances = np.sqrt((rpm_norm - ref_rpm_norm)**2 + (tps_norm - ref_tps_norm)**2)

        # Check for exact match
        min_dist = np.min(distances)
        if min_dist < 0.01:
            return float(self._correction_ratios[np.argmin(distances)])

        # Inverse distance weighting (IDW)
        # Use power of 2 for smoother interpolation
        power = 2.0
        weights = 1.0 / np.power(distances, power)

        # Normalize weights
        weights = weights / np.sum(weights)

        # Weighted average of corrections
        interpolated = float(np.sum(weights * self._correction_ratios))

        # Blend toward average correction as we get further from all reference points
        # This prevents wild extrapolation far from measured data
        max_reference_dist = np.min(distances)  # Distance to nearest reference point
        blend_distance = 20.0  # Start blending when nearest point is 20 units away (normalized)
        if max_reference_dist > blend_distance:
            blend_factor = min(1.0, (max_reference_dist - blend_distance) / blend_distance)
            interpolated = (1.0 - blend_factor) * interpolated + blend_factor * self._avg_correction

        return interpolated

    def predict_corrected_ve(self, rpm: float, tps: float, base_ve: float) -> float:
        """Predict corrected VE for a cell.

        Args:
            rpm: Engine RPM
            tps: Throttle position (0-100%)
            base_ve: Base VE from the map for this cell

        Returns:
            Corrected VE value
        """
        correction = self.predict_correction(rpm, tps)
        return base_ve * correction

    def get_fit_quality_description(self) -> str:
        """Get human-readable description of fit quality."""
        if self.fit_stats is None:
            return "Model not fitted"

        r2 = self.fit_stats.r_squared
        if r2 >= 0.95:
            quality = "Excellent"
        elif r2 >= 0.85:
            quality = "Good"
        elif r2 >= 0.70:
            quality = "Fair"
        else:
            quality = "Poor"

        return f"{quality} (R² = {r2:.3f})"


class EngineConfigManager:
    """Manager for loading/saving engine configurations."""

    @staticmethod
    def get_configs_file() -> Path:
        """Get path to engine configurations file."""
        from mfviewer.utils.config import TabConfiguration
        config_dir = TabConfiguration.get_default_config_dir()
        return config_dir / 'engine_configs.json'

    @classmethod
    def load_configs(cls) -> Dict[str, EngineConfig]:
        """Load all saved engine configurations.

        Returns:
            Dictionary mapping config name to EngineConfig
        """
        configs_file = cls.get_configs_file()
        if not configs_file.exists():
            return {}

        try:
            with open(configs_file, 'r') as f:
                data = json.load(f)

            configs = {}
            for name, config_dict in data.items():
                try:
                    configs[name] = EngineConfig.from_dict(config_dict)
                except (KeyError, TypeError):
                    continue  # Skip invalid configs

            return configs

        except (json.JSONDecodeError, IOError):
            return {}

    @classmethod
    def save_config(cls, config: EngineConfig):
        """Save or update an engine configuration.

        Args:
            config: Configuration to save
        """
        configs = cls.load_configs()
        configs[config.name] = config

        configs_file = cls.get_configs_file()
        configs_file.parent.mkdir(parents=True, exist_ok=True)

        # Convert to serializable dict
        data = {name: cfg.to_dict() for name, cfg in configs.items()}

        try:
            with open(configs_file, 'w') as f:
                json.dump(data, f, indent=2)
        except IOError as e:
            print(f"Failed to save engine config: {e}")

    @classmethod
    def delete_config(cls, name: str) -> bool:
        """Delete a saved engine configuration.

        Args:
            name: Name of configuration to delete

        Returns:
            True if deleted, False if not found
        """
        configs = cls.load_configs()
        if name not in configs:
            return False

        del configs[name]

        configs_file = cls.get_configs_file()
        data = {n: cfg.to_dict() for n, cfg in configs.items()}

        try:
            with open(configs_file, 'w') as f:
                json.dump(data, f, indent=2)
            return True
        except IOError:
            return False

    @classmethod
    def get_config_names(cls) -> List[str]:
        """Get list of saved configuration names."""
        configs = cls.load_configs()
        return sorted(configs.keys())
