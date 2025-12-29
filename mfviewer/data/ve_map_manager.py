"""
VE Map Manager - Handles loading, saving, and managing Fuel VE maps.

This module provides functionality for:
- Loading VE maps from CSV files
- Saving modified VE maps to CSV
- Managing default and user map paths
"""

import csv
import numpy as np
from pathlib import Path
from typing import Tuple, List, Optional

from mfviewer.utils.config import TabConfiguration


class VEMapManager:
    """Manages VE map data operations including loading, saving, and path management."""

    def __init__(self, config_dir: Optional[Path] = None):
        """
        Initialize the VE Map Manager.

        Args:
            config_dir: Optional custom config directory. If None, uses default AppData path.
        """
        self.config_dir = config_dir or TabConfiguration.get_default_config_dir()
        self._default_map_path = Path(__file__).parent / "base_fuel_ve_map.csv"

    @staticmethod
    def load_map(file_path: Path) -> Tuple[np.ndarray, List[float], List[float], str]:
        """
        Load a VE map from a CSV file.

        The CSV format expected:
        - Row 1: Header with load type label, followed by RPM breakpoints
        - Rows 2+: Load value in first column, then VE values across RPM

        Args:
            file_path: Path to the CSV file

        Returns:
            Tuple of (ve_values, rpm_axis, load_axis, load_type)
            - ve_values: 2D numpy array of VE percentages
            - rpm_axis: List of RPM breakpoints (columns)
            - load_axis: List of Load breakpoints (rows)
            - load_type: String indicating load type (e.g., "TPS" or "MAP")

        Raises:
            FileNotFoundError: If the file doesn't exist
            ValueError: If the file format is invalid
        """
        if not file_path.exists():
            raise FileNotFoundError(f"VE map file not found: {file_path}")

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader)

                # Parse header - first cell contains load type info
                load_label = header[0]
                load_type = "TPS" if "TPS" in load_label else "MAP"

                # Extract RPM axis from header (skip first cell)
                rpm_axis = [float(x) for x in header[1:]]

                # Read data rows
                load_axis = []
                ve_values = []

                for row in reader:
                    if not row or not row[0].strip():
                        continue  # Skip empty rows

                    load_axis.append(float(row[0]))
                    ve_values.append([float(x) for x in row[1:]])

                # Validate dimensions
                if not ve_values:
                    raise ValueError("No data rows found in VE map file")

                expected_cols = len(rpm_axis)
                for i, row in enumerate(ve_values):
                    if len(row) != expected_cols:
                        raise ValueError(
                            f"Row {i+2} has {len(row)} values, expected {expected_cols}"
                        )

                return np.array(ve_values, dtype=np.float32), rpm_axis, load_axis, load_type

        except Exception as e:
            raise ValueError(f"Failed to parse VE map file: {e}")

    @staticmethod
    def save_map(file_path: Path, ve_values: np.ndarray,
                 rpm_axis: List[float], load_axis: List[float],
                 load_type: str = "TPS") -> bool:
        """
        Save a VE map to a CSV file.

        Args:
            file_path: Path to save the CSV file
            ve_values: 2D numpy array of VE percentages
            rpm_axis: List of RPM breakpoints (columns)
            load_axis: List of Load breakpoints (rows)
            load_type: Type of load axis ("TPS" or "MAP")

        Returns:
            True if successful, False otherwise
        """
        try:
            # Ensure parent directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)

            with open(file_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)

                # Write header
                load_label = f"Fuel - Load ({load_type}) (%)"
                header = [load_label] + [str(int(rpm) if rpm == int(rpm) else rpm) for rpm in rpm_axis]
                writer.writerow(header)

                # Write data rows
                for i, load_val in enumerate(load_axis):
                    row = [str(load_val)]
                    row.extend([f"{v:.1f}" for v in ve_values[i]])
                    writer.writerow(row)

                return True

        except Exception as e:
            print(f"Error saving VE map: {e}")
            return False

    def get_default_map_path(self) -> Path:
        """
        Get path to the default base map (bundled with application).

        Returns:
            Path to the default base_fuel_ve_map.csv
        """
        return self._default_map_path

    def get_user_map_path(self, filename: str = "user_fuel_ve_map.csv") -> Path:
        """
        Get path for user's custom base map in AppData.

        Args:
            filename: Name of the map file

        Returns:
            Path in the user's config directory
        """
        return self.config_dir / filename

    def get_corrected_map_path(self, original_name: str = "corrected") -> Path:
        """
        Get a unique path for saving a corrected map.

        Args:
            original_name: Base name for the corrected map

        Returns:
            Path for the corrected map file
        """
        base_path = self.config_dir / f"{original_name}_fuel_ve_map.csv"

        # If file exists, add a number suffix
        if base_path.exists():
            counter = 1
            while True:
                new_path = self.config_dir / f"{original_name}_fuel_ve_map_{counter}.csv"
                if not new_path.exists():
                    return new_path
                counter += 1

        return base_path

    def copy_default_to_user(self) -> bool:
        """
        Copy the default base map to user's config directory.

        Returns:
            True if successful, False otherwise
        """
        try:
            default_path = self.get_default_map_path()
            user_path = self.get_user_map_path()

            if not default_path.exists():
                return False

            # Load and save to copy
            ve_values, rpm_axis, load_axis, load_type = self.load_map(default_path)
            return self.save_map(user_path, ve_values, rpm_axis, load_axis, load_type)

        except Exception:
            return False

    def list_saved_maps(self) -> List[Path]:
        """
        List all VE map files in the user's config directory.

        Returns:
            List of paths to VE map CSV files
        """
        if not self.config_dir.exists():
            return []

        return list(self.config_dir.glob("*_ve_map*.csv"))


def find_bin_index(value: float, axis: List[float]) -> int:
    """
    Find the bin index for a value using the axis breakpoints as bin boundaries.

    For VE maps, each cell represents a range:
    - For ascending axis (RPM): bin[i] covers from axis[i] to axis[i+1]
    - For descending axis (Load): bin[i] covers from axis[i] down to axis[i+1]

    The value is assigned to the bin whose breakpoint it is closest to or just past.

    Args:
        value: The value to bin
        axis: List of axis breakpoints (can be ascending or descending)

    Returns:
        Index of the bin (0 to len(axis)-1)
    """
    if len(axis) == 0:
        return 0

    if len(axis) == 1:
        return 0

    # Detect if axis is descending (e.g., load axis: 100, 90, 80, ... 0)
    is_descending = axis[0] > axis[-1]

    if is_descending:
        # Descending axis (e.g., Load: 100, 90, 80, ... 0)
        # Value 95 should go to bin 0 (100%), value 85 to bin 1 (90%), etc.
        if value >= axis[0]:
            return 0
        if value <= axis[-1]:
            return len(axis) - 1

        # Find the bin where value falls between axis[i] and axis[i+1]
        for i in range(len(axis) - 1):
            if value <= axis[i] and value > axis[i + 1]:
                return i

        return len(axis) - 1
    else:
        # Ascending axis (e.g., RPM: 0, 250, 500, ...)
        # Value 125 should go to bin 0, value 375 to bin 1 (250), etc.
        if value <= axis[0]:
            return 0
        if value >= axis[-1]:
            return len(axis) - 1

        # Find the bin where value falls between axis[i] and axis[i+1]
        for i in range(len(axis) - 1):
            if value >= axis[i] and value < axis[i + 1]:
                return i

        return len(axis) - 1


def interpolate_bin_value(value: float, axis: List[float]) -> Tuple[int, int, float]:
    """
    Find the two nearest bins and interpolation factor for a value.

    This is useful for weighted distribution of samples across bins.

    Args:
        value: The value to interpolate
        axis: List of axis breakpoints (must be sorted)

    Returns:
        Tuple of (lower_bin_idx, upper_bin_idx, interpolation_factor)
        - interpolation_factor: 0.0 = all weight on lower, 1.0 = all weight on upper
    """
    if len(axis) < 2:
        return 0, 0, 0.0

    if value <= axis[0]:
        return 0, 0, 0.0
    if value >= axis[-1]:
        idx = len(axis) - 1
        return idx, idx, 0.0

    # Find the bracketing bins
    for i in range(1, len(axis)):
        if value <= axis[i]:
            lower_idx = i - 1
            upper_idx = i

            # Calculate interpolation factor
            span = axis[upper_idx] - axis[lower_idx]
            if span > 0:
                factor = (value - axis[lower_idx]) / span
            else:
                factor = 0.0

            return lower_idx, upper_idx, factor

    # Shouldn't reach here, but fallback
    idx = len(axis) - 1
    return idx, idx, 0.0
