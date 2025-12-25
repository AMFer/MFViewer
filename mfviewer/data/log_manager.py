"""
Log file manager for multi-log comparison.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from mfviewer.data.parser import TelemetryData


@dataclass
class LogFile:
    """Container for a single log file with metadata."""
    index: int                    # Position in list (0-based)
    file_path: Path
    telemetry: TelemetryData
    is_active: bool
    display_name: str            # Filename by default
    color_offset: int            # Offset for color cycling
    time_offset: float = 0.0     # Time offset in seconds (positive = shift right, negative = shift left)


class LogFileManager:
    """Manages multiple telemetry log files for comparison."""

    def __init__(self):
        self.log_files: List[LogFile] = []
        self._next_index = 0

    def add_log_file(self, file_path: Path, telemetry: TelemetryData,
                     is_active: bool = True) -> LogFile:
        """
        Add a log file to the manager.

        Args:
            file_path: Path to the log file
            telemetry: Parsed telemetry data
            is_active: Whether the log should be active (checked)

        Returns:
            The created LogFile object
        """
        # Create display name from filename
        display_name = file_path.name

        # Calculate color offset (each log gets different offset)
        color_offset = len(self.log_files) * 2

        log_file = LogFile(
            index=self._next_index,
            file_path=file_path,
            telemetry=telemetry,
            is_active=is_active,
            display_name=display_name,
            color_offset=color_offset
        )

        self.log_files.append(log_file)
        self._next_index += 1

        return log_file

    def remove_log_file(self, index: int) -> None:
        """
        Remove a log file from the manager.

        Args:
            index: Index of the log file to remove
        """
        self.log_files = [log for log in self.log_files if log.index != index]

    def set_active(self, index: int, active: bool) -> None:
        """
        Set the active state of a log file.

        Args:
            index: Index of the log file
            active: New active state
        """
        for log in self.log_files:
            if log.index == index:
                log.is_active = active
                break

    def get_main_log(self) -> Optional[LogFile]:
        """
        Get the main log (first active log).

        Returns:
            The first active log file, or None if no logs are active
        """
        for log in self.log_files:
            if log.is_active:
                return log
        return None

    def get_active_logs(self) -> List[LogFile]:
        """
        Get all active log files in order.

        Returns:
            List of active log files, ordered by their position in the list
        """
        return [log for log in self.log_files if log.is_active]

    def get_log_at(self, index: int) -> Optional[LogFile]:
        """
        Get log file by index.

        Args:
            index: Index of the log file

        Returns:
            The log file if found, None otherwise
        """
        for log in self.log_files:
            if log.index == index:
                return log
        return None

    def set_time_offset(self, index: int, new_offset: float) -> None:
        """
        Set the time offset for a log file.

        This applies the offset directly to the telemetry data, so all channels
        will have the correct time values.

        Args:
            index: Index of the log file
            new_offset: Time offset in seconds (positive = shift right/later, negative = shift left/earlier)
        """
        for log in self.log_files:
            if log.index == index:
                # Calculate the delta from current offset to new offset
                delta = new_offset - log.time_offset
                if delta != 0.0:
                    # Apply the delta to the telemetry data
                    log.telemetry.apply_time_offset(delta)
                    log.time_offset = new_offset
                break

    def reset_all_time_offsets(self) -> None:
        """Reset all time offsets to use original timestamps."""
        for log in self.log_files:
            if log.time_offset != 0.0:
                # Reverse the current offset
                log.telemetry.apply_time_offset(-log.time_offset)
                log.time_offset = 0.0

    def auto_align_to_zero(self) -> None:
        """
        Automatically align all logs to start at time 0.
        This applies an offset to each log's telemetry data so that its first timestamp becomes 0.
        """
        for log in self.log_files:
            time_range = log.telemetry.get_time_range()
            if time_range:
                # Calculate offset to negate the first timestamp
                new_offset = -time_range[0]
                # Calculate delta from current offset
                delta = new_offset - log.time_offset
                if delta != 0.0:
                    # Apply the delta to the telemetry data
                    log.telemetry.apply_time_offset(delta)
                    log.time_offset = new_offset
