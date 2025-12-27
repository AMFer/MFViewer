"""
Time-series plotting widget using PyQtGraph.

Performance features:
- GPU-accelerated array operations via CuPy (when available)
- OpenGL rendering for smooth plotting
- Level of Detail (LOD) support for large datasets
"""

from typing import Dict, Optional, List, Tuple
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QListWidget, QListWidgetItem, QSplitter, QCheckBox, QMenu
)
from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QMouseEvent, QAction, QPen
import pyqtgraph as pg
import numpy as np
from pathlib import Path

from mfviewer.data.parser import ChannelInfo, TelemetryData

# Try to enable OpenGL for better performance
try:
    import pyqtgraph.opengl as gl
    pg.setConfigOption('useOpenGL', True)
    pg.setConfigOption('enableExperimental', True)
    OPENGL_AVAILABLE = True
except ImportError:
    OPENGL_AVAILABLE = False

# Try to import CuPy for GPU-accelerated array operations
CUPY_AVAILABLE = False
try:
    import cupy as cp
    # Verify CUDA is actually available
    cp.cuda.runtime.getDeviceCount()
    CUPY_AVAILABLE = True
except (ImportError, Exception):
    pass


def filter_nan_values(time_data: np.ndarray, values: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Filter out NaN values from time and value arrays.

    Uses CuPy (GPU) if available for faster processing on large arrays.
    Falls back to NumPy for CPU processing.

    Args:
        time_data: Array of time values
        values: Array of data values

    Returns:
        Tuple of (filtered_time, filtered_values)
    """
    # Only use GPU for larger arrays where transfer overhead is worth it
    if CUPY_AVAILABLE and len(values) > 10000:
        try:
            # Transfer to GPU
            values_gpu = cp.asarray(values)

            # Compute mask on GPU
            mask = ~cp.isnan(values_gpu)

            # Apply mask and transfer back to CPU
            time_data_gpu = cp.asarray(time_data)
            filtered_time = time_data_gpu[mask].get()
            filtered_values = values_gpu[mask].get()

            return filtered_time, filtered_values
        except Exception:
            # Fall back to CPU if GPU operation fails
            pass

    # CPU fallback (NumPy)
    mask = ~np.isnan(values)
    return time_data[mask], values[mask]


def compute_statistics_gpu(values: np.ndarray) -> dict:
    """
    Compute statistics using GPU if available.

    Args:
        values: Array of values

    Returns:
        Dict with min, max, mean statistics
    """
    if CUPY_AVAILABLE and len(values) > 50000:
        try:
            values_gpu = cp.asarray(values)
            return {
                'min': float(cp.nanmin(values_gpu).get()),
                'max': float(cp.nanmax(values_gpu).get()),
                'mean': float(cp.nanmean(values_gpu).get()),
            }
        except Exception:
            pass

    # CPU fallback
    return {
        'min': float(np.nanmin(values)),
        'max': float(np.nanmax(values)),
        'mean': float(np.nanmean(values)),
    }


# Line styles for multi-log comparison (up to 5 logs)
# Using Qt.PenStyle for basic style, then custom dash patterns for visibility
LOG_LINE_STYLES = [
    Qt.PenStyle.SolidLine,      # Main log (1st)
    Qt.PenStyle.DashLine,       # 2nd log
    Qt.PenStyle.DotLine,        # 3rd log
    Qt.PenStyle.DashDotLine,    # 4th log
    Qt.PenStyle.DashDotDotLine, # 5th log
]

# Custom dash patterns for better visibility (values are in pen width units)
# Format: [dash, gap, dash, gap, ...]
LOG_DASH_PATTERNS = [
    None,                    # Solid line - no pattern needed
    [15, 8],                 # Long dash: 15px dash, 8px gap
    [3, 6],                  # Dots: 3px dot, 6px gap
    [15, 6, 3, 6],           # Dash-dot: 15px dash, 6px gap, 3px dot, 6px gap
    [15, 5, 3, 5, 3, 5],     # Dash-dot-dot: dash, gap, dot, gap, dot, gap
]


def get_line_style_for_log(active_index: int) -> Qt.PenStyle:
    """Get line style for a log based on its position in active logs."""
    return LOG_LINE_STYLES[active_index % len(LOG_LINE_STYLES)]


def apply_custom_dash_pattern(pen: QPen, active_index: int) -> QPen:
    """Apply custom dash pattern to pen for better visibility."""
    pattern_idx = active_index % len(LOG_DASH_PATTERNS)
    pattern = LOG_DASH_PATTERNS[pattern_idx]
    if pattern is not None:
        pen.setDashPattern(pattern)
    return pen


class PlotWidget(QWidget):
    """Widget for plotting telemetry data."""

    def __init__(self, units_manager=None):
        super().__init__()
        self.telemetry: Optional[TelemetryData] = None
        self.plot_items: Dict[Tuple[str, int], dict] = {}  # (channel_name, log_index) -> plot_info
        self.units_manager = units_manager  # For unit conversions and display

        # Pending channels to plot when data becomes available
        # This preserves channel configuration when no logs are loaded
        self.pending_channels: set = set()

        # Exclude outliers setting (default: True)
        self.exclude_outliers = True

        # Callback for removing this plot
        self.remove_callback = None

        # Container reference for context menu access
        self.container = None

        # Log manager reference for multi-log support
        self.log_manager = None

        # Cursor synchronization
        self.cursor_line = None
        self.cursor_x_position = None
        self.cursor_callback = None  # Callback to sync cursor across plots

        # Enable drag and drop
        self.setAcceptDrops(True)

        # Enable context menu
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        self._setup_ui()

    def _setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Plot area
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('#1e1e1e')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setLabel('bottom', 'Time', units='s', color='#dcdcdc')
        # No Y-axis label to save space - units shown in legend instead

        # Enable drag and drop on the plot widget itself and install event filter
        self.plot_widget.setAcceptDrops(True)
        self.plot_widget.installEventFilter(self)

        # Performance optimizations
        self.plot_widget.setClipToView(True)  # Only render visible data
        self.plot_widget.setDownsampling(mode='peak')  # Downsample for performance
        self.plot_widget.setAntialiasing(False)  # Disable antialiasing for speed

        # Reduce update frequency for smoother interaction
        self.plot_widget.setMouseEnabled(x=True, y=True)
        self.plot_widget.setMenuEnabled(False)  # Disable context menu for speed

        # Style the plot axes
        axis_pen = pg.mkPen(color='#3e3e42', width=1)
        self.plot_widget.getAxis('bottom').setPen(axis_pen)
        self.plot_widget.getAxis('left').setPen(axis_pen)
        self.plot_widget.getAxis('bottom').setTextPen('#dcdcdc')
        self.plot_widget.getAxis('left').setTextPen('#dcdcdc')

        # Add legend with dark styling
        self.legend = self.plot_widget.addLegend()
        self.legend.setBrush('#2d2d30')

        # Install event filter on legend to handle clicks
        self.legend.scene().installEventFilter(self)
        self._last_click_pos = None

        # Create cursor line (initially hidden)
        self.cursor_line = pg.InfiniteLine(
            pos=0,
            angle=90,
            pen=pg.mkPen(color='#ffff00', width=1, style=Qt.PenStyle.DashLine),
            movable=False
        )
        self.cursor_line.setVisible(False)
        self.plot_widget.addItem(self.cursor_line)

        # Track if cursor is active and being dragged
        self.cursor_active = False
        self.cursor_dragging = False

        # Install event filter on the plot widget to capture mouse events
        self.plot_widget.viewport().installEventFilter(self)

        layout.addWidget(self.plot_widget)

    def eventFilter(self, obj, event):
        """Filter events to detect double-clicks on legend items, handle drag/drop, and cursor dragging."""
        # Handle legend double-click first (higher priority)
        if event.type() == QEvent.Type.GraphicsSceneMouseDoubleClick:
            # Get the position in scene coordinates
            scene_pos = event.scenePos()

            # Check if click is within legend bounds
            if self.legend.sceneBoundingRect().contains(scene_pos):
                # Convert to legend's local coordinates
                local_pos = self.legend.mapFromScene(scene_pos)

                # Find which item was clicked
                for sample, label in self.legend.items:
                    if label.boundingRect().contains(label.mapFromParent(local_pos)):
                        # Extract channel name from label text (may include "(Log N)" suffix)
                        label_text = label.text
                        # Remove value part after colon if present
                        if ':' in label_text:
                            label_text = label_text.split(':', 1)[0].strip()

                        # Check if this is a multi-log label like "Channel (Log 2)"
                        # and extract the base channel name
                        channel_name = label_text
                        if ' (Log ' in label_text:
                            channel_name = label_text.rsplit(' (Log ', 1)[0]

                        # Remove the channel (from all logs)
                        self.remove_channel(channel_name)
                        return True

        # Handle mouse events on the plot viewport for cursor dragging
        if obj == self.plot_widget.viewport():
            if event.type() == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton and self.plot_items:
                    # Check if mouse is not over legend before starting cursor drag
                    view_pos = self.plot_widget.mapFromGlobal(event.globalPosition().toPoint())
                    scene_pos = self.plot_widget.mapToScene(view_pos)
                    if not self.legend.sceneBoundingRect().contains(scene_pos):
                        self.cursor_dragging = True
                        self.cursor_active = True
                        self._update_cursor_from_mouse_event(event)
                    return False  # Let the event propagate for pan/zoom
            elif event.type() == QEvent.Type.MouseButtonRelease:
                if event.button() == Qt.MouseButton.LeftButton:
                    self.cursor_dragging = False
                    return False
            elif event.type() == QEvent.Type.MouseMove:
                if self.cursor_dragging and self.cursor_active and self.plot_items:
                    self._update_cursor_from_mouse_event(event)
                    return False  # Let the event propagate for pan/zoom

        # Handle drag/drop events from child plot_widget
        if obj == self.plot_widget:
            if event.type() == QEvent.Type.DragEnter:
                if event.mimeData().hasText():
                    event.acceptProposedAction()
                    return True
            elif event.type() == QEvent.Type.DragMove:
                if event.mimeData().hasText():
                    event.acceptProposedAction()
                    return True
            elif event.type() == QEvent.Type.Drop:
                if event.mimeData().hasText():
                    channel_name = event.mimeData().text()
                    if self.telemetry:
                        channel = self.telemetry.get_channel(channel_name)
                        if channel:
                            self.add_channel(channel, self.telemetry)
                            event.acceptProposedAction()
                            return True

        return super().eventFilter(obj, event)

    def get_channel_names(self) -> List[str]:
        """
        Get list of channel names currently plotted or pending.

        Returns:
            List of channel names (includes both plotted and pending channels)
        """
        # Extract unique channel names from tuple keys, plus any pending channels
        plotted = set(key[0] for key in self.plot_items.keys())
        return list(plotted | self.pending_channels)

    def get_y_range(self) -> Optional[Tuple[float, float]]:
        """
        Get the current Y-axis range.

        Returns:
            Tuple of (min, max) as native Python floats, or None if no range set
        """
        view_range = self.plot_widget.viewRange()
        if view_range and len(view_range) >= 2:
            y_range = view_range[1]  # [0] is X, [1] is Y
            if y_range and len(y_range) >= 2:
                # Convert to native Python float for JSON serialization
                return (float(y_range[0]), float(y_range[1]))
        return None

    def set_y_range(self, y_min: float, y_max: float):
        """
        Set the Y-axis range.

        Args:
            y_min: Minimum Y value
            y_max: Maximum Y value
        """
        self.plot_widget.setYRange(y_min, y_max, padding=0)

    def add_channel(self, channel: ChannelInfo, telemetry: TelemetryData,
                    active_index: int = 0, log_file_path: Optional[Path] = None):
        """
        Add a channel to the plot.

        Args:
            channel: Channel metadata
            telemetry: Telemetry data object
            active_index: Index in active logs list (0 for main log)
            log_file_path: Path to the log file (optional)
        """
        # Check if already plotted with tuple key
        plot_key = (channel.name, active_index)
        if plot_key in self.plot_items:
            # Channel already plotted for this log
            return

        self.telemetry = telemetry

        # Get channel data
        data_series = telemetry.get_channel_data(channel.name)
        if data_series is None:
            return

        # Get time data (index) - time offset is already applied to telemetry data
        time_data = data_series.index.to_numpy()
        values = data_series.to_numpy()

        # Apply unit conversions if units_manager is available
        if self.units_manager:
            # Use the channel's data_type from the log file header
            values = self.units_manager.apply_channel_conversion(channel.name, values, channel.data_type)

        # Remove NaN values for cleaner plotting (uses GPU if available)
        time_data, values = filter_nan_values(time_data, values)

        if len(time_data) == 0:
            return

        # Choose color based on channel name only (same color across all logs)
        # This way all instances of "RPM" have the same color regardless of log
        colors = [
            (255, 90, 90),     # Bright Red
            (90, 200, 255),    # Bright Blue
            (100, 255, 100),   # Bright Green
            (255, 200, 90),    # Bright Orange
            (220, 120, 255),   # Bright Purple
            (90, 240, 220),    # Bright Cyan
            (255, 100, 200),   # Bright Pink
            (240, 240, 100),   # Bright Yellow
        ]
        # Get existing unique channels (by name only)
        existing_channel_names = sorted(set(key[0] for key in self.plot_items.keys()))
        # Check if this channel already has a color assigned
        if channel.name in existing_channel_names:
            # Reuse the same color as existing entries for this channel
            color_idx = existing_channel_names.index(channel.name)
        else:
            # New channel - assign next color
            color_idx = len(existing_channel_names)
        color = colors[color_idx % len(colors)]

        # Get line style based on log position (different line styles for each log)
        line_style = get_line_style_for_log(active_index)

        # Add plot item with style and custom dash pattern for better visibility
        pen = pg.mkPen(color=color, width=2, style=line_style)
        apply_custom_dash_pattern(pen, active_index)

        # Only add legend entry for first occurrence of channel (from first log)
        # Subsequent logs for same channel don't get separate legend entries
        is_first_for_channel = not any(key[0] == channel.name for key in self.plot_items.keys())
        legend_name = channel.name if is_first_for_channel else None

        # Convert to float64 for pyqtgraph to avoid overflow in ViewBox calculations
        plot_item = self.plot_widget.plot(
            time_data.astype(np.float64),
            values.astype(np.float64),
            pen=pen,
            name=legend_name  # None means no legend entry
        )

        # Store reference with new structure
        self.plot_items[plot_key] = {
            'plot_item': plot_item,
            'channel': channel,
            'color': color,
            'log_index': active_index,
            'log_file_path': log_file_path,
            'line_style': line_style
        }

        # Auto-range to fit all data
        self._auto_scale()

    def add_channel_from_all_logs(self, channel_name: str, log_manager):
        """
        Plot a channel from all active logs.

        Args:
            channel_name: Channel to plot
            log_manager: LogFileManager instance
        """
        active_logs = log_manager.get_active_logs() if log_manager else []

        if not active_logs:
            # No logs available - store as pending channel
            self.pending_channels.add(channel_name)
            return

        # Remove from pending since we're plotting it now
        self.pending_channels.discard(channel_name)

        for active_index, log_file in enumerate(active_logs):
            channel = log_file.telemetry.get_channel(channel_name)

            if channel:
                # Time offset is already applied to telemetry data, no need to pass it
                self.add_channel(
                    channel=channel,
                    telemetry=log_file.telemetry,
                    active_index=active_index,
                    log_file_path=log_file.file_path
                )
            # Skip logs that don't have this channel

    def _auto_scale(self):
        """
        Auto-scale the plot to fit all data.
        If 'Exclude Outliers' is checked, removes outliers on a per-channel basis before scaling.
        For Percentage type channels, always use 0-100 range.
        Auto-scales both X and Y axes; global sync will harmonize X-ranges across plots.
        """
        if not self.plot_items:
            return

        # Calculate X-range from all plotted data
        x_min = None
        x_max = None
        for plot_info in self.plot_items.values():
            plot_item = plot_info['plot_item']
            x_data = plot_item.xData
            if x_data is not None and len(x_data) > 0:
                if x_min is None or x_data.min() < x_min:
                    x_min = x_data.min()
                if x_max is None or x_data.max() > x_max:
                    x_max = x_data.max()

        # Set X-range if we have data
        if x_min is not None and x_max is not None:
            self.plot_widget.setXRange(x_min, x_max, padding=0.02)

        # Check if all channels are Percentage type - if so, use fixed 0-100 range
        all_percentage = all(
            plot_info['channel'].data_type == 'Percentage'
            for plot_info in self.plot_items.values()
        )
        if all_percentage:
            self.plot_widget.setYRange(0, 100, padding=0)
            return

        if self.exclude_outliers:
            # Calculate range excluding outliers per channel (using IQR method)
            overall_min = None
            overall_max = None

            for plot_info in self.plot_items.values():
                plot_item = plot_info['plot_item']
                y_data = plot_item.yData

                if y_data is not None and len(y_data) > 0:
                    # Convert to numpy array and remove NaN values
                    channel_values = np.array(y_data)
                    channel_values = channel_values[~np.isnan(channel_values)]

                    if len(channel_values) > 0:
                        # Calculate IQR for this channel only
                        q1 = np.percentile(channel_values, 25)
                        q3 = np.percentile(channel_values, 75)
                        iqr = q3 - q1

                        # Define outlier bounds (10.0 * IQR for excluding only extremely aberrant values)
                        # Standard is 1.5 * IQR; 10.0 only removes sensor errors and corrupt data
                        lower_bound = q1 - 10.0 * iqr
                        upper_bound = q3 + 10.0 * iqr

                        # Filter values within bounds for this channel
                        filtered_values = channel_values[
                            (channel_values >= lower_bound) & (channel_values <= upper_bound)
                        ]

                        if len(filtered_values) > 0:
                            channel_min = np.min(filtered_values)
                            channel_max = np.max(filtered_values)

                            # Update overall min/max
                            if overall_min is None or channel_min < overall_min:
                                overall_min = channel_min
                            if overall_max is None or channel_max > overall_max:
                                overall_max = channel_max

            # Set Y range based on filtered data from all channels
            if overall_min is not None and overall_max is not None:
                # Add 5% padding
                padding = (overall_max - overall_min) * 0.05
                self.plot_widget.setYRange(overall_min - padding, overall_max + padding, padding=0)
                return

        # If not excluding outliers or no data, auto-range Y only
        self.plot_widget.enableAutoRange(axis='y')

    def remove_channel(self, channel_name: str, log_index: Optional[int] = None):
        """
        Remove channel from plot.

        Args:
            channel_name: Channel to remove
            log_index: If specified, remove only this log's version.
                       If None, remove from all logs.
        """
        if log_index is not None:
            # Remove specific log
            plot_key = (channel_name, log_index)
            if plot_key in self.plot_items:
                self.plot_widget.removeItem(self.plot_items[plot_key]['plot_item'])
                del self.plot_items[plot_key]
        else:
            # Remove all logs
            keys_to_remove = [k for k in self.plot_items.keys() if k[0] == channel_name]
            for key in keys_to_remove:
                self.plot_widget.removeItem(self.plot_items[key]['plot_item'])
                del self.plot_items[key]
            # Also remove from pending channels
            self.pending_channels.discard(channel_name)

    def clear_all_plots(self):
        """Clear all visual plots but preserve pending channel configuration."""
        # Clear visual plot items directly (don't use remove_channel to preserve pending)
        for plot_key, plot_info in list(self.plot_items.items()):
            self.plot_widget.removeItem(plot_info['plot_item'])

        # Clear the plot widget
        self.plot_widget.clear()
        self.plot_items.clear()
        # Note: pending_channels is intentionally NOT cleared here

        # Re-add grid and legend with dark theme
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.legend = self.plot_widget.addLegend()
        self.legend.setBrush('#2d2d30')

        # Reinstall event filter for legend clicks
        self.legend.scene().installEventFilter(self)

        # Re-add cursor line
        self.cursor_line = pg.InfiniteLine(
            pos=0,
            angle=90,
            pen=pg.mkPen(color='#ffff00', width=1, style=Qt.PenStyle.DashLine),
            movable=False
        )
        self.cursor_line.setVisible(False)
        self.plot_widget.addItem(self.cursor_line)

        # Reset cursor active state
        self.cursor_active = False
        self.cursor_dragging = False

    def _toggle_exclude_outliers(self):
        """Toggle the exclude outliers setting and refresh the plot."""
        self.exclude_outliers = not self.exclude_outliers
        self._auto_scale()

    def refresh_with_new_telemetry(self, new_telemetry: 'TelemetryData'):
        """
        Refresh all plotted channels with new telemetry data.
        This is called when a new log file is loaded (single-log mode).
        For multi-log mode, use refresh_with_multi_log() instead.

        Args:
            new_telemetry: New telemetry data object
        """
        if not new_telemetry or not self.plot_items:
            return

        self.telemetry = new_telemetry

        # Store current plot info with tuple keys
        plots_to_replot = [
            (plot_key, plot_info['channel'].name, plot_info['color'],
             plot_info['line_style'], plot_info.get('log_file_path'))
            for plot_key, plot_info in self.plot_items.items()
        ]
        cursor_pos = self.cursor_x_position

        # Clear all plots
        self.clear_all_plots()

        # Track which channels have had legend entries added
        channels_with_legend = set()

        # Re-add all channels from new telemetry
        for plot_key, channel_name, original_color, line_style, log_file_path in plots_to_replot:
            original_channel_name, log_index = plot_key

            # Get channel from new telemetry
            channel = new_telemetry.get_channel(channel_name)
            if not channel:
                # Channel doesn't exist in new file, skip it
                continue

            # Get channel data
            data_series = new_telemetry.get_channel_data(channel_name)
            if data_series is None:
                continue

            # Get time data (index) - time offset is already applied to telemetry data
            time_data = data_series.index.to_numpy()
            values = data_series.to_numpy()

            # Apply unit conversions if units_manager is available
            if self.units_manager:
                # Use the channel's data_type from the log file header
                values = self.units_manager.apply_channel_conversion(channel_name, values, channel.data_type)

            # Remove NaN values for cleaner plotting
            mask = ~np.isnan(values)
            time_data = time_data[mask]
            values = values[mask]

            if len(time_data) == 0:
                continue

            # Add plot item with original color and style with custom dash pattern
            pen = pg.mkPen(color=original_color, width=2, style=line_style)
            apply_custom_dash_pattern(pen, log_index)

            # Only add legend entry for first occurrence of each channel
            legend_name = None
            if channel.name not in channels_with_legend:
                legend_name = channel.name
                channels_with_legend.add(channel.name)

            # Convert to float64 for pyqtgraph to avoid overflow in ViewBox calculations
            plot_item = self.plot_widget.plot(
                time_data.astype(np.float64),
                values.astype(np.float64),
                pen=pen,
                name=legend_name  # None means no legend entry
            )

            # Store reference with tuple key
            self.plot_items[plot_key] = {
                'plot_item': plot_item,
                'channel': channel,
                'color': original_color,
                'log_index': log_index,
                'log_file_path': log_file_path,
                'line_style': line_style
            }

        # Auto-range to fit all data
        self._auto_scale()

        # Restore cursor position if it was active (but don't restore exact position since time range might be different)
        if cursor_pos is not None and self.cursor_active:
            # Reset cursor to start of new data
            time_range = new_telemetry.get_time_range()
            if time_range:
                self.set_cursor_position(time_range[0])

    def refresh_with_new_units(self):
        """Refresh all plotted channels with new unit conversions."""
        if not self.plot_items:
            return

        # For multi-log scenarios, use log_manager if available
        if self.log_manager:
            # Collect unique channel names
            channel_names = set(key[0] for key in self.plot_items.keys())
            cursor_pos = self.cursor_x_position
            cursor_active = self.cursor_active

            # Clear all and re-add from all active logs
            self.clear_all_plots()

            for channel_name in channel_names:
                self.add_channel_from_all_logs(channel_name, self.log_manager)

            # Auto-range to fit all data
            self._auto_scale()

            # Restore cursor position if it was active
            if cursor_pos is not None and cursor_active:
                self.set_cursor_position(cursor_pos)
            return

        # Fallback for single-log mode
        if not self.telemetry:
            return

        # Store current plot info with tuple keys
        plots_to_replot = [
            (plot_key, plot_info['channel'], plot_info['color'],
             plot_info['line_style'], plot_info.get('log_file_path'))
            for plot_key, plot_info in self.plot_items.items()
        ]
        cursor_pos = self.cursor_x_position

        # Clear all plots
        self.clear_all_plots()

        # Track which channels have had legend entries added
        channels_with_legend = set()

        # Re-add all channels with new unit conversions
        for plot_key, channel, original_color, line_style, log_file_path in plots_to_replot:
            channel_name, log_index = plot_key

            # Get channel data
            data_series = self.telemetry.get_channel_data(channel.name)
            if data_series is None:
                continue

            # Get time data (index) - time offset is already applied to telemetry data
            time_data = data_series.index.to_numpy()
            values = data_series.to_numpy()

            # Apply unit conversions if units_manager is available
            if self.units_manager:
                # Use the channel's data_type from the log file header
                values = self.units_manager.apply_channel_conversion(channel.name, values, channel.data_type)

            # Remove NaN values for cleaner plotting
            mask = ~np.isnan(values)
            time_data = time_data[mask]
            values = values[mask]

            if len(time_data) == 0:
                continue

            # Add plot item with original color and style with custom dash pattern
            pen = pg.mkPen(color=original_color, width=2, style=line_style)
            apply_custom_dash_pattern(pen, log_index)

            # Only add legend entry for first occurrence of each channel
            legend_name = None
            if channel.name not in channels_with_legend:
                legend_name = channel.name
                channels_with_legend.add(channel.name)

            # Convert to float64 for pyqtgraph to avoid overflow in ViewBox calculations
            plot_item = self.plot_widget.plot(
                time_data.astype(np.float64),
                values.astype(np.float64),
                pen=pen,
                name=legend_name  # None means no legend entry
            )

            # Store reference with tuple key
            self.plot_items[plot_key] = {
                'plot_item': plot_item,
                'channel': channel,
                'color': original_color,
                'log_index': log_index,
                'log_file_path': log_file_path,
                'line_style': line_style
            }

        # Auto-range to fit all data
        self._auto_scale()

        # Restore cursor position if it was active
        if cursor_pos is not None and self.cursor_active:
            self.set_cursor_position(cursor_pos)

    def refresh_with_multi_log(self, log_manager):
        """
        Refresh all plotted channels from current active logs.

        Args:
            log_manager: LogFileManager instance
        """
        # Collect unique channel names from both plotted items and pending channels
        channel_names = set(key[0] for key in self.plot_items.keys()) | self.pending_channels

        if not channel_names:
            return

        # Save cursor state before clearing
        cursor_pos = self.cursor_x_position
        was_cursor_active = self.cursor_active

        # Clear all visual plots
        self.clear_all_plots()

        # Store log manager reference
        self.log_manager = log_manager

        # Check if there are any active logs
        active_logs = log_manager.get_active_logs() if log_manager else []

        if not active_logs:
            # No logs available - store channels as pending for later
            self.pending_channels = channel_names
        else:
            # Clear pending channels since we're about to plot them
            self.pending_channels.clear()

            # Re-plot from active logs
            for channel_name in channel_names:
                self.add_channel_from_all_logs(channel_name, log_manager)

            # Restore cursor state if it was active
            if was_cursor_active and cursor_pos is not None and self.plot_items:
                self.cursor_active = True
                self.set_cursor_position(cursor_pos)

    def dragEnterEvent(self, event):
        """Handle drag enter event."""
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        """Handle drag move event."""
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        """Handle drop event - add channel to plot from all active logs."""
        if event.mimeData().hasText():
            # The text contains the channel name
            channel_name = event.mimeData().text()

            # Use log_manager to add from all active logs if available
            if self.log_manager:
                self.add_channel_from_all_logs(channel_name, self.log_manager)
                event.acceptProposedAction()
            elif self.telemetry:
                # Fallback to single telemetry (legacy support)
                # Time offset is already applied to telemetry data
                channel = self.telemetry.get_channel(channel_name)
                if channel:
                    self.add_channel(channel, self.telemetry)
                    event.acceptProposedAction()

    def _show_context_menu(self, position):
        """Show context menu for plot actions."""
        menu = QMenu(self)

        # Add plot action (calls container's add plot method)
        if self.container and hasattr(self.container, 'add_plot'):
            add_plot_action = QAction("Add Plot", self)
            add_plot_action.triggered.connect(self.container.add_plot)
            menu.addAction(add_plot_action)
            menu.addSeparator()

        # Layout orientation actions (calls container's methods)
        if self.container and hasattr(self.container, 'set_layout_orientation'):
            horizontal_action = QAction("Horizontal Layout", self)
            horizontal_action.triggered.connect(lambda: self.container.set_layout_orientation(Qt.Orientation.Horizontal))
            menu.addAction(horizontal_action)

            vertical_action = QAction("Vertical Layout", self)
            vertical_action.triggered.connect(lambda: self.container.set_layout_orientation(Qt.Orientation.Vertical))
            menu.addAction(vertical_action)
            menu.addSeparator()

        # Auto scale action
        auto_scale_action = QAction("Auto Scale", self)
        auto_scale_action.triggered.connect(self._auto_scale)
        menu.addAction(auto_scale_action)

        # Exclude outliers toggle
        exclude_outliers_action = QAction("Exclude Outliers", self)
        exclude_outliers_action.setCheckable(True)
        exclude_outliers_action.setChecked(self.exclude_outliers)
        exclude_outliers_action.triggered.connect(self._toggle_exclude_outliers)
        menu.addAction(exclude_outliers_action)

        menu.addSeparator()

        # Clear all action
        clear_action = QAction("Clear All Channels", self)
        clear_action.triggered.connect(self.clear_all_plots)
        menu.addAction(clear_action)

        # Remove plot action (only if callback is set and there are multiple plots)
        if self.remove_callback:
            menu.addSeparator()
            remove_action = QAction("Remove This Plot", self)
            remove_action.triggered.connect(lambda: self.remove_callback(self))
            menu.addAction(remove_action)

        menu.exec(self.mapToGlobal(position))

    def _update_cursor_from_mouse_event(self, event):
        """
        Update cursor position from a mouse event.

        Args:
            event: QMouseEvent from the viewport
        """
        # Get mouse position in widget coordinates
        pos = event.pos()

        # Convert to scene coordinates
        scene_pos = self.plot_widget.mapToScene(pos)

        # Get viewbox
        vb = self.plot_widget.getViewBox()
        if vb is None:
            return

        # Convert to data coordinates
        mouse_point = vb.mapSceneToView(scene_pos)
        x_pos = mouse_point.x()

        # Update cursor position through callback
        if self.cursor_callback:
            self.cursor_callback(x_pos)
        else:
            self.set_cursor_position(x_pos)

    def set_cursor_position(self, x_pos: float):
        """
        Set cursor position and update legend with values.
        Snaps cursor to data boundaries if clicked outside the data range.

        Args:
            x_pos: X position for the cursor
        """
        # Snap cursor to data range if we have plot items
        snapped_x_pos = x_pos
        if self.plot_items:
            snapped_x_pos = self._snap_to_data_range(x_pos)

        self.cursor_x_position = snapped_x_pos

        # Always show and position cursor line (even if no data)
        if self.cursor_line:
            self.cursor_line.setPos(snapped_x_pos)
            self.cursor_line.setVisible(True)

        # Update legend with values at cursor position (only if we have data)
        if self.plot_items:
            self._update_legend_with_cursor_values(snapped_x_pos)

    def _snap_to_data_range(self, x_pos: float) -> float:
        """
        Snap x position to the data range boundaries if outside.

        Args:
            x_pos: Requested x position

        Returns:
            x position clamped to data range
        """
        if not self.plot_items:
            return x_pos

        # Find the global data range across all plot items
        x_min = None
        x_max = None

        for plot_info in self.plot_items.values():
            plot_item = plot_info['plot_item']
            if plot_item.xData is not None and len(plot_item.xData) > 0:
                item_min = plot_item.xData[0]
                item_max = plot_item.xData[-1]

                if x_min is None or item_min < x_min:
                    x_min = item_min
                if x_max is None or item_max > x_max:
                    x_max = item_max

        # Clamp to range if we have data
        if x_min is not None and x_max is not None:
            if x_pos < x_min:
                return x_min
            elif x_pos > x_max:
                return x_max

        return x_pos

    def _update_legend_with_cursor_values(self, x_pos: float):
        """
        Update legend to show values at cursor position from all logs.

        Args:
            x_pos: X position to read values from
        """
        if not self.legend:
            return

        # Find the maximum log index to know how many value slots to show
        max_log_index = max((key[1] for key in self.plot_items.keys()), default=0)

        # Update legend labels with values from all logs
        for sample, label in self.legend.items:
            # Find the channel name from the current label text
            # Split on ':' to separate name from value
            parts = label.text.split(':', 1)
            channel_name = parts[0].strip()

            # Collect values from all logs for this channel
            values_list = []
            unit_str = ''
            channel_type = None

            for log_idx in range(max_log_index + 1):
                plot_key = (channel_name, log_idx)
                if plot_key in self.plot_items:
                    plot_info = self.plot_items[plot_key]
                    plot_item = plot_info['plot_item']
                    channel = plot_info['channel']

                    # Get unit from first available channel
                    if channel_type is None:
                        channel_type = channel.data_type
                        if self.units_manager:
                            unit = self.units_manager.get_unit(channel_name, use_preference=True, channel_type=channel_type)
                            if unit:
                                unit_str = f" {unit}"

                    # Get value at cursor position
                    value_str = self._get_value_at_position(plot_item, x_pos, channel_name)
                    values_list.append(value_str if value_str else '--')
                else:
                    # Channel doesn't exist in this log
                    values_list.append('--')

            # Format the label with all values side-by-side
            if any(v != '--' for v in values_list):
                values_display = ' | '.join(values_list)
                label.setText(f"{channel_name}: {values_display}{unit_str}")
            else:
                label.setText(f"{channel_name}{unit_str}")

    def _get_value_at_position(self, plot_item, x_pos: float, channel_name: str = None) -> Optional[str]:
        """
        Get interpolated value at a given x position.

        Args:
            plot_item: The plot item to get value from
            x_pos: X position to interpolate value at
            channel_name: Optional channel name for state label lookup

        Returns:
            Formatted value string or None
        """
        if plot_item.xData is None or plot_item.yData is None:
            return None

        x_data = plot_item.xData
        y_data = plot_item.yData

        if len(x_data) == 0 or len(y_data) == 0:
            return None

        # Find closest point or interpolate
        # If x_pos is outside data range, clamp to nearest boundary
        if x_pos < x_data[0]:
            value = y_data[0]
        elif x_pos > x_data[-1]:
            value = y_data[-1]
        else:
            # Find the two nearest points for interpolation
            idx = np.searchsorted(x_data, x_pos)

            if idx == 0:
                value = y_data[0]
            elif idx >= len(x_data):
                value = y_data[-1]
            else:
                # Linear interpolation
                x0, x1 = x_data[idx - 1], x_data[idx]
                y0, y1 = y_data[idx - 1], y_data[idx]

                if x1 == x0:
                    value = y0
                else:
                    # Interpolate
                    t = (x_pos - x0) / (x1 - x0)
                    value = y0 + t * (y1 - y0)

        # Format value
        if np.isnan(value):
            return None

        # Check for state mapping (e.g., Idle Control State)
        if channel_name and self.units_manager:
            state_label = self.units_manager.get_state_label(channel_name, value)
            if state_label:
                return f"{int(round(value))} ({state_label})"

        # Format to appropriate precision
        if abs(value) >= 1000:
            return f"{value:.1f}"
        elif abs(value) >= 10:
            return f"{value:.2f}"
        else:
            return f"{value:.3f}"
