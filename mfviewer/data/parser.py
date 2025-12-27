"""
MF log file parser with performance optimizations.

This module handles parsing of telemetry log files in CSV format.
The format consists of a metadata header section followed by time-series data.

Performance features:
- GPU acceleration via cuDF (NVIDIA CUDA) with Polars/pandas fallback
- Parquet caching for instant repeat loads
- Vectorized time parsing (10-50x faster than apply())
- Float32 data types for 50% memory reduction
- Pre-computed downsampling (LOD) for smooth pan/zoom
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Callable
import numpy as np
from pathlib import Path
import hashlib
import json

# Import pandas as base (always available)
import pandas as pd

# Try to import GPU-accelerated libraries
CUDF_AVAILABLE = False
POLARS_AVAILABLE = False
PYARROW_AVAILABLE = False

try:
    import cudf
    CUDF_AVAILABLE = True
except ImportError:
    pass

try:
    import polars as pl
    POLARS_AVAILABLE = True
except ImportError:
    pass

try:
    import pyarrow.parquet as pq
    import pyarrow as pa
    PYARROW_AVAILABLE = True
except ImportError:
    pass


def get_parser_backend() -> str:
    """Return the name of the active parsing backend."""
    if CUDF_AVAILABLE:
        return "cuDF (GPU)"
    elif POLARS_AVAILABLE:
        return "Polars"
    else:
        return "pandas"


@dataclass
class ChannelInfo:
    """Metadata for a single telemetry channel."""
    name: str
    channel_id: int
    data_type: str
    min_value: float  # Display min from header (configuration)
    max_value: float  # Display max from header (configuration)
    column_index: int
    # Pre-computed actual data statistics (computed at parse time for faster auto-scale)
    data_min: Optional[float] = None
    data_max: Optional[float] = None
    data_q1: Optional[float] = None  # 25th percentile for outlier detection
    data_q3: Optional[float] = None  # 75th percentile for outlier detection

    @property
    def display_range(self) -> Tuple[float, float]:
        """Get the display range as a tuple (min, max)."""
        return (self.min_value, self.max_value)

    @property
    def data_range(self) -> Optional[Tuple[float, float]]:
        """Get the actual data range as a tuple (min, max), or None if not computed."""
        if self.data_min is not None and self.data_max is not None:
            return (self.data_min, self.data_max)
        return None

    @property
    def iqr(self) -> Optional[float]:
        """Get the interquartile range (Q3 - Q1), or None if not computed."""
        if self.data_q1 is not None and self.data_q3 is not None:
            return self.data_q3 - self.data_q1
        return None

    def __repr__(self) -> str:
        return f"Channel({self.name}, ID={self.channel_id}, type={self.data_type})"


class ParquetCache:
    """Manages Parquet-based caching of parsed data for instant reload."""

    def __init__(self, cache_dir: Optional[Path] = None):
        """Initialize cache with optional custom directory."""
        if cache_dir is None:
            # Use platform-appropriate cache directory
            from platformdirs import user_cache_dir
            cache_dir = Path(user_cache_dir("MFViewer", "MFViewer")) / "parsed_data"

        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_suffix = ".meta.json"

    def _get_file_hash(self, file_path: Path) -> str:
        """Generate hash based on file path, size, and modification time."""
        stat = file_path.stat()
        hash_input = f"{file_path.absolute()}:{stat.st_size}:{stat.st_mtime}"
        return hashlib.md5(hash_input.encode()).hexdigest()[:16]

    def _get_cache_paths(self, file_path: Path) -> Tuple[Path, Path]:
        """Get paths for cached data and metadata files."""
        file_hash = self._get_file_hash(file_path)
        base_name = f"{file_path.stem}_{file_hash}"
        return (
            self.cache_dir / f"{base_name}.parquet",
            self.cache_dir / f"{base_name}{self.metadata_suffix}"
        )

    def get_cached(self, file_path: Path) -> Optional[Tuple[pd.DataFrame, List[dict], Dict[str, str]]]:
        """Load cached data if available and valid."""
        if not PYARROW_AVAILABLE:
            return None

        parquet_path, meta_path = self._get_cache_paths(file_path)

        if not parquet_path.exists() or not meta_path.exists():
            return None

        try:
            # Load DataFrame from Parquet
            df = pd.read_parquet(parquet_path)

            # Load metadata
            with open(meta_path, 'r') as f:
                meta = json.load(f)

            return df, meta['channels'], meta['metadata']
        except Exception:
            # Cache corrupted, will be regenerated
            return None

    def save_to_cache(self, file_path: Path, df: pd.DataFrame,
                      channels: List['ChannelInfo'], metadata: Dict[str, str]):
        """Save parsed data to cache."""
        if not PYARROW_AVAILABLE:
            return

        parquet_path, meta_path = self._get_cache_paths(file_path)

        try:
            # Save DataFrame to Parquet
            df.to_parquet(parquet_path, index=True)

            # Save metadata (channels as dicts)
            channel_dicts = [
                {
                    'name': ch.name,
                    'channel_id': ch.channel_id,
                    'data_type': ch.data_type,
                    'min_value': ch.min_value,
                    'max_value': ch.max_value,
                    'column_index': ch.column_index,
                    # Pre-computed statistics
                    'data_min': ch.data_min,
                    'data_max': ch.data_max,
                    'data_q1': ch.data_q1,
                    'data_q3': ch.data_q3,
                }
                for ch in channels
            ]

            with open(meta_path, 'w') as f:
                json.dump({'channels': channel_dicts, 'metadata': metadata}, f)
        except Exception as e:
            print(f"Warning: Failed to save cache: {e}")

    def clear_cache(self):
        """Clear all cached files."""
        for f in self.cache_dir.glob("*.parquet"):
            f.unlink()
        for f in self.cache_dir.glob(f"*{self.metadata_suffix}"):
            f.unlink()


# Global cache instance
_cache = None

def get_cache() -> ParquetCache:
    """Get or create the global cache instance."""
    global _cache
    if _cache is None:
        _cache = ParquetCache()
    return _cache


class MFLogParser:
    """
    Parser for telemetry log files with GPU acceleration and caching.

    The log file format:
    - Header: %DataLog%, version, software info
    - Metadata: Channel definitions (Channel, ID, Type, DisplayMaxMin)
    - Log info: Log Source, Log Number, Log timestamp
    - Data: CSV rows with timestamp + channel values

    Performance optimizations:
    - cuDF (GPU) > Polars > pandas fallback chain
    - Parquet caching for instant repeat loads
    - Vectorized time parsing
    - Float32 data types for memory efficiency
    """

    def __init__(self, file_path: str, use_cache: bool = True,
                 progress_callback: Optional[Callable[[int, str], None]] = None):
        """
        Initialize parser with a log file path.

        Args:
            file_path: Path to the .csv log file
            use_cache: Whether to use Parquet caching (default True)
            progress_callback: Optional callback(percent, message) for progress updates
        """
        self.file_path = Path(file_path)
        self.metadata: Dict[str, str] = {}
        self.channels: List[ChannelInfo] = []
        self.data: Optional[pd.DataFrame] = None
        self._data_start_line: int = 0
        self.use_cache = use_cache
        self.progress_callback = progress_callback or (lambda p, m: None)

        # Downsampled data for LOD (Level of Detail)
        self.downsampled_data: Dict[int, pd.DataFrame] = {}

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

        # Try to load from cache first
        if self.use_cache:
            self.progress_callback(5, "Checking cache...")
            cached = get_cache().get_cached(self.file_path)
            if cached is not None:
                self.progress_callback(10, "Loading from cache...")
                df, channel_dicts, self.metadata = cached
                self.data = df
                self.channels = [
                    ChannelInfo(**ch) for ch in channel_dicts
                ]
                self.progress_callback(100, "Loaded from cache")
                return TelemetryData(
                    data=self.data,
                    channels=self.channels,
                    metadata=self.metadata,
                    file_path=self.file_path,
                    downsampled_data=self.downsampled_data
                )

        # Parse metadata and channel definitions
        self.progress_callback(10, "Parsing metadata...")
        self._parse_metadata()

        # Parse data section using best available backend
        self.progress_callback(20, f"Loading data ({get_parser_backend()})...")
        self._parse_data()

        # Process time column with vectorized operations
        self.progress_callback(70, "Processing time column...")
        self._process_time_column_vectorized()

        # Pre-compute channel statistics for faster auto-scale
        self.progress_callback(80, "Computing channel statistics...")
        self._compute_channel_statistics()

        # Pre-compute downsampled data for LOD
        self.progress_callback(85, "Computing downsampled data...")
        self._compute_downsampled_data()

        # Save to cache for future loads
        if self.use_cache:
            self.progress_callback(95, "Saving to cache...")
            get_cache().save_to_cache(
                self.file_path, self.data, self.channels, self.metadata
            )

        self.progress_callback(100, "Complete")
        return TelemetryData(
            data=self.data,
            channels=self.channels,
            metadata=self.metadata,
            file_path=self.file_path,
            downsampled_data=self.downsampled_data
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
        """Parse the data section using the best available backend."""
        if self._data_start_line == 0:
            raise ValueError("No data section found in file")

        # Build column names: Time + channel names
        column_names = ['Time'] + [ch.name for ch in self.channels]
        skip_rows = self._data_start_line - 1

        # Build dtype dict for float32 (memory optimization)
        # Keep Time as string for now, will process separately
        dtypes = {ch.name: 'float32' for ch in self.channels}

        if CUDF_AVAILABLE:
            self._parse_with_cudf(column_names, skip_rows, dtypes)
        elif POLARS_AVAILABLE:
            self._parse_with_polars(column_names, skip_rows)
        else:
            self._parse_with_pandas(column_names, skip_rows, dtypes)

    def _parse_with_cudf(self, column_names: List[str], skip_rows: int, dtypes: dict):
        """Parse CSV using cuDF (GPU-accelerated)."""
        try:
            # cuDF dtype specification
            cudf_dtypes = {'Time': 'str'}
            cudf_dtypes.update({k: 'float32' for k in dtypes.keys()})

            df = cudf.read_csv(
                self.file_path,
                skiprows=skip_rows,
                names=column_names,
                header=None,
                dtype=cudf_dtypes,
                na_values=['', ' '],
            )

            # Convert to pandas for compatibility with rest of application
            self.data = df.to_pandas()
        except Exception as e:
            print(f"cuDF parsing failed, falling back to Polars: {e}")
            if POLARS_AVAILABLE:
                self._parse_with_polars(column_names, skip_rows)
            else:
                self._parse_with_pandas(column_names, skip_rows, dtypes)

    def _parse_with_polars(self, column_names: List[str], skip_rows: int):
        """Parse CSV using Polars (fast CPU-based)."""
        try:
            # Polars is extremely fast for CSV parsing
            df = pl.read_csv(
                self.file_path,
                skip_rows=skip_rows,
                has_header=False,
                new_columns=column_names,
                null_values=['', ' '],
                dtypes={ch.name: pl.Float32 for ch in self.channels},
            )

            # Convert to pandas for compatibility
            self.data = df.to_pandas()
        except Exception as e:
            print(f"Polars parsing failed, falling back to pandas: {e}")
            dtypes = {ch.name: 'float32' for ch in self.channels}
            self._parse_with_pandas(column_names, skip_rows, dtypes)

    def _parse_with_pandas(self, column_names: List[str], skip_rows: int, dtypes: dict):
        """Parse CSV using pandas (fallback)."""
        try:
            self.data = pd.read_csv(
                self.file_path,
                skiprows=skip_rows,
                names=column_names,
                header=None,
                encoding='utf-8',
                na_values=['', ' '],
                dtype=dtypes,
                low_memory=False
            )
        except Exception as e:
            raise ValueError(f"Failed to parse data section: {e}")

    def _process_time_column_vectorized(self):
        """
        Convert Time column using vectorized operations.

        This is 10-50x faster than using apply() with a Python function.
        """
        if self.data is None or 'Time' not in self.data.columns:
            return

        # Vectorized time parsing using pandas string operations
        time_col = self.data['Time'].astype(str)

        # Split into components: HH:MM:SS.mmm
        time_parts = time_col.str.split(':', expand=True)

        # Convert each component to numeric
        hours = pd.to_numeric(time_parts[0], errors='coerce')
        minutes = pd.to_numeric(time_parts[1], errors='coerce')
        seconds = pd.to_numeric(time_parts[2], errors='coerce')

        # Calculate total seconds
        self.data['Seconds'] = (hours * 3600 + minutes * 60 + seconds).astype('float32')

        # Normalize time to start at 0
        first_time = self.data['Seconds'].iloc[0]
        if not np.isnan(first_time):
            self.data['Seconds'] = self.data['Seconds'] - first_time

        # Set Seconds as index for time-series operations
        self.data.set_index('Seconds', inplace=True)

    def _compute_channel_statistics(self):
        """
        Pre-compute statistics for each channel at parse time.

        This computes min, max, Q1, Q3 for each channel, which are used by
        the plot widget for faster auto-scale operations. Computing these
        once during parsing avoids redundant calculations during plotting.
        """
        if self.data is None:
            return

        for channel in self.channels:
            if channel.name not in self.data.columns:
                continue

            try:
                # Get channel data as numpy array
                values = self.data[channel.name].to_numpy()

                # Remove NaN values for statistics
                clean_values = values[~np.isnan(values)]

                if len(clean_values) > 0:
                    channel.data_min = float(np.min(clean_values))
                    channel.data_max = float(np.max(clean_values))
                    channel.data_q1 = float(np.percentile(clean_values, 25))
                    channel.data_q3 = float(np.percentile(clean_values, 75))
            except Exception:
                # If statistics computation fails, leave as None
                pass

    def _compute_downsampled_data(self):
        """
        Pre-compute downsampled versions of data for Level of Detail (LOD) rendering.

        Creates downsampled versions at 10x, 100x, and 1000x reduction factors,
        preserving min/max peaks within each window for accurate visualization.
        """
        if self.data is None or len(self.data) < 1000:
            return  # No need for downsampling on small datasets

        for factor in [10, 100, 1000]:
            if len(self.data) >= factor * 10:  # Only if meaningful reduction
                self.downsampled_data[factor] = self._downsample_minmax(factor)

    def _downsample_minmax(self, factor: int) -> pd.DataFrame:
        """
        Downsample data while preserving min/max peaks.

        This ensures that spikes and peaks are visible even at low zoom levels.
        For each window of 'factor' points, we keep both the min and max values.
        """
        n_rows = len(self.data)
        n_groups = n_rows // factor

        if n_groups < 2:
            return self.data.copy()

        # Create group indices
        indices = np.arange(n_rows) // factor
        indices = indices[:n_groups * factor]  # Trim to exact multiple

        # Get data subset
        data_subset = self.data.iloc[:n_groups * factor]

        # Use only numeric columns for aggregation
        numeric_cols = data_subset.select_dtypes(include=[np.number]).columns.tolist()

        # Group and compute min/max
        grouped = data_subset[numeric_cols].groupby(indices)
        min_vals = grouped.min()
        max_vals = grouped.max()

        # Interleave min and max for peak preservation
        # This doubles the number of points but ensures peaks are visible
        result = pd.concat([min_vals, max_vals]).sort_index(kind='stable')

        # Compute average time index for each group
        time_index = data_subset.index.to_series().groupby(indices).mean()

        # Duplicate time index for interleaved data
        new_index = np.repeat(time_index.values, 2)
        result.index = new_index
        result.index.name = 'Seconds'

        return result


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
                 file_path: Path,
                 downsampled_data: Optional[Dict[int, pd.DataFrame]] = None):
        """
        Initialize TelemetryData.

        Args:
            data: DataFrame with telemetry data
            channels: List of channel metadata
            metadata: Global metadata from file header
            file_path: Path to source file
            downsampled_data: Optional pre-computed downsampled versions
        """
        self.data = data
        self.channels = channels
        self.metadata = metadata
        self.file_path = file_path
        self.downsampled_data = downsampled_data or {}

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

    def get_channel_data(self, channel_name: str,
                         downsample_factor: Optional[int] = None) -> Optional[pd.Series]:
        """
        Get data series for a specific channel.

        Args:
            channel_name: Name of the channel
            downsample_factor: Optional factor (10, 100, 1000) for LOD

        Returns:
            Pandas Series with the channel data, or None if not found
        """
        # Use downsampled data if requested and available
        if downsample_factor and downsample_factor in self.downsampled_data:
            data_source = self.downsampled_data[downsample_factor]
        else:
            data_source = self.data

        if channel_name in data_source.columns:
            return data_source[channel_name]
        return None

    def get_time_range(self) -> Tuple[float, float]:
        """
        Get the time range of the data.

        Returns:
            Tuple of (start_time, end_time) in seconds
        """
        if self.data.index.name == 'Seconds':
            return (float(self.data.index.min()), float(self.data.index.max()))
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

    def get_optimal_downsample_factor(self, visible_points: int,
                                       target_points: int = 2000) -> Optional[int]:
        """
        Get the optimal downsampling factor for the current view.

        Args:
            visible_points: Number of data points in the visible range
            target_points: Target number of points to display

        Returns:
            Downsample factor (10, 100, 1000) or None for full resolution
        """
        if visible_points <= target_points:
            return None

        ratio = visible_points / target_points

        if ratio > 500 and 1000 in self.downsampled_data:
            return 1000
        elif ratio > 50 and 100 in self.downsampled_data:
            return 100
        elif ratio > 5 and 10 in self.downsampled_data:
            return 10

        return None

    def __repr__(self) -> str:
        time_range = self.get_time_range()
        backend = get_parser_backend()
        return (f"TelemetryData(file={self.file_path.name}, "
                f"channels={len(self.channels)}, "
                f"samples={len(self.data)}, "
                f"duration={time_range[1]-time_range[0]:.1f}s, "
                f"backend={backend})")
