"""
MF log file parser.

This module handles parsing of telemetry log files in CSV format.
The format consists of a metadata header section followed by time-series data.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
from pathlib import Path


@dataclass
class ChannelInfo:
    """Metadata for a single telemetry channel."""
    name: str
    channel_id: int
    data_type: str
    min_value: float
    max_value: float
    column_index: int

    @property
    def display_range(self) -> Tuple[float, float]:
        """Get the display range as a tuple (min, max)."""
        return (self.min_value, self.max_value)

    def __repr__(self) -> str:
        return f"Channel({self.name}, ID={self.channel_id}, type={self.data_type})"


class MFLogParser:
    """
    Parser for telemetry log files.

    The log file format:
    - Header: %DataLog%, version, software info
    - Metadata: Channel definitions (Channel, ID, Type, DisplayMaxMin)
    - Log info: Log Source, Log Number, Log timestamp
    - Data: CSV rows with timestamp + channel values
    """

    def __init__(self, file_path: str):
        """
        Initialize parser with a log file path.

        Args:
            file_path: Path to the .csv log file
        """
        self.file_path = Path(file_path)
        self.metadata: Dict[str, str] = {}
        self.channels: List[ChannelInfo] = []
        self.data: Optional[pd.DataFrame] = None
        self._data_start_line: int = 0

    def parse(self) -> 'TelemetryData':
        """
        Parse the log file and return a TelemetryData object.

        Returns:
            TelemetryData object containing parsed data and metadata

        Raises:
            FileNotFoundError: If the log file doesn't exist
            ValueError: If the file format is invalid
        """
        if not self.file_path.exists():
            raise FileNotFoundError(f"Log file not found: {self.file_path}")

        # Parse metadata and channel definitions
        self._parse_metadata()

        # Parse data section
        self._parse_data()

        return TelemetryData(
            data=self.data,
            channels=self.channels,
            metadata=self.metadata,
            file_path=self.file_path
        )

    def _parse_metadata(self):
        """Parse the metadata header section to extract channel information."""
        current_channel = {}
        channel_index = 0  # Tracks position in data columns (0 is Time)

        with open(self.file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()

                # Check if we've reached the data section
                # Data lines start with timestamp pattern HH:MM:SS
                if line and line[0].isdigit() and ':' in line[:8]:
                    self._data_start_line = line_num
                    break

                # Parse key-value pairs
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip()
                    value = value.strip()

                    # Global metadata
                    if key in ['DataLogVersion', 'Software', 'SoftwareVersion',
                               'DownloadDateTime', 'Log Source', 'Log Number', 'Log']:
                        self.metadata[key] = value

                    # Channel metadata
                    elif key == 'Channel':
                        # Save previous channel if exists
                        if current_channel:
                            self._add_channel(current_channel, channel_index)
                            channel_index += 1
                        # Start new channel
                        current_channel = {'name': value}

                    elif key == 'ID':
                        current_channel['id'] = int(value)

                    elif key == 'Type':
                        current_channel['type'] = value

                    elif key == 'DisplayMaxMin':
                        # Format: "max,min"
                        max_val, min_val = value.split(',')
                        current_channel['max'] = float(max_val)
                        current_channel['min'] = float(min_val)

            # Don't forget the last channel
            if current_channel:
                self._add_channel(current_channel, channel_index)

    def _add_channel(self, channel_dict: dict, column_index: int):
        """Create ChannelInfo from dict and add to channels list."""
        try:
            channel = ChannelInfo(
                name=channel_dict['name'],
                channel_id=channel_dict.get('id', 0),
                data_type=channel_dict.get('type', 'Unknown'),
                min_value=channel_dict.get('min', 0.0),
                max_value=channel_dict.get('max', 100.0),
                column_index=column_index + 1  # +1 because column 0 is Time
            )
            self.channels.append(channel)
        except KeyError as e:
            print(f"Warning: Incomplete channel definition, missing {e}")

    def _parse_data(self):
        """Parse the data section into a pandas DataFrame."""
        if self._data_start_line == 0:
            raise ValueError("No data section found in file")

        # Build column names: Time + channel names
        column_names = ['Time'] + [ch.name for ch in self.channels]

        # Read CSV data starting from the data line
        # skiprows: skip header lines, use 0-based indexing
        skip_rows = self._data_start_line - 1

        try:
            self.data = pd.read_csv(
                self.file_path,
                skiprows=skip_rows,
                names=column_names,
                header=None,
                encoding='utf-8',
                na_values=['', ' '],  # Handle empty values as NaN
                low_memory=False
            )

            # Convert Time column to proper datetime/timedelta format
            self._process_time_column()

        except Exception as e:
            raise ValueError(f"Failed to parse data section: {e}")

    def _process_time_column(self):
        """Convert Time column from HH:MM:SS.mmm string to usable format."""
        if self.data is None or 'Time' not in self.data.columns:
            return

        # Convert to timedelta (seconds since start)
        def parse_time(time_str):
            """Parse HH:MM:SS.mmm to seconds as float."""
            try:
                parts = str(time_str).split(':')
                if len(parts) != 3:
                    return np.nan

                hours = float(parts[0])
                minutes = float(parts[1])
                seconds = float(parts[2])

                return hours * 3600 + minutes * 60 + seconds
            except (ValueError, AttributeError):
                return np.nan

        # Create seconds column
        self.data['Seconds'] = self.data['Time'].apply(parse_time)

        # Normalize time to start at 0 by subtracting the first timestamp
        first_time = self.data['Seconds'].iloc[0]
        if not np.isnan(first_time):
            self.data['Seconds'] = self.data['Seconds'] - first_time

        # Set Seconds as index for time-series operations
        self.data.set_index('Seconds', inplace=True)


class TelemetryData:
    """
    Container for parsed telemetry data with metadata.

    This class wraps the parsed DataFrame along with channel information
    and provides convenient access methods.
    """

    def __init__(self,
                 data: pd.DataFrame,
                 channels: List[ChannelInfo],
                 metadata: Dict[str, str],
                 file_path: Path):
        """
        Initialize TelemetryData.

        Args:
            data: DataFrame with telemetry data
            channels: List of channel metadata
            metadata: Global metadata from file header
            file_path: Path to source file
        """
        self.data = data
        self.channels = channels
        self.metadata = metadata
        self.file_path = file_path

        # Build lookup dictionaries
        self._channel_by_name = {ch.name: ch for ch in channels}
        self._channel_by_id = {ch.channel_id: ch for ch in channels}

    def get_channel(self, name: str) -> Optional[ChannelInfo]:
        """Get channel metadata by name."""
        return self._channel_by_name.get(name)

    def get_channel_by_id(self, channel_id: int) -> Optional[ChannelInfo]:
        """Get channel metadata by ID."""
        return self._channel_by_id.get(channel_id)

    def get_channel_names(self) -> List[str]:
        """Get list of all channel names."""
        return [ch.name for ch in self.channels]

    def get_channel_data(self, channel_name: str) -> Optional[pd.Series]:
        """
        Get data series for a specific channel.

        Args:
            channel_name: Name of the channel

        Returns:
            Pandas Series with the channel data, or None if not found
        """
        if channel_name in self.data.columns:
            return self.data[channel_name]
        return None

    def get_time_range(self) -> Tuple[float, float]:
        """
        Get the time range of the data.

        Returns:
            Tuple of (start_time, end_time) in seconds
        """
        if self.data.index.name == 'Seconds':
            return (self.data.index.min(), self.data.index.max())
        return (0.0, 0.0)

    def get_statistics(self, channel_name: str) -> Optional[Dict[str, float]]:
        """
        Get statistics for a channel.

        Args:
            channel_name: Name of the channel

        Returns:
            Dictionary with min, max, mean, std, or None if channel not found
        """
        data = self.get_channel_data(channel_name)
        if data is None:
            return None

        return {
            'min': float(data.min()),
            'max': float(data.max()),
            'mean': float(data.mean()),
            'std': float(data.std()),
            'count': int(data.count())
        }

    def __repr__(self) -> str:
        time_range = self.get_time_range()
        return (f"TelemetryData(file={self.file_path.name}, "
                f"channels={len(self.channels)}, "
                f"samples={len(self.data)}, "
                f"duration={time_range[1]-time_range[0]:.1f}s)")
