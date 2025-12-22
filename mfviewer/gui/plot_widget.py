"""
Time-series plotting widget using PyQtGraph.
"""

from typing import Dict, Optional, List
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QListWidget, QListWidgetItem, QSplitter, QCheckBox, QMenu
)
from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QMouseEvent, QAction
import pyqtgraph as pg
import numpy as np

from mfviewer.data.parser import ChannelInfo, TelemetryData

# Try to enable OpenGL for better performance
try:
    import pyqtgraph.opengl as gl
    pg.setConfigOption('useOpenGL', True)
    pg.setConfigOption('enableExperimental', True)
    OPENGL_AVAILABLE = True
except ImportError:
    OPENGL_AVAILABLE = False


class PlotWidget(QWidget):
    """Widget for plotting telemetry data."""

    def __init__(self):
        super().__init__()
        self.telemetry: Optional[TelemetryData] = None
        self.plot_items: Dict[str, dict] = {}  # channel_name -> {plot_item, data_item}

        # Exclude outliers setting (default: True)
        self.exclude_outliers = True

        # Callback for removing this plot
        self.remove_callback = None

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
        self.plot_widget.setLabel('left', 'Value', color='#dcdcdc')

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

        layout.addWidget(self.plot_widget)

    def eventFilter(self, obj, event):
        """Filter events to detect double-clicks on legend items and handle drag/drop."""
        # Handle legend double-click
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
                        channel_name = label.text
                        self.remove_channel(channel_name)
                        return True

        # Handle drag/drop events from child plot_widget
        elif obj == self.plot_widget:
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
        Get list of channel names currently plotted.

        Returns:
            List of channel names
        """
        return list(self.plot_items.keys())

    def add_channel(self, channel: ChannelInfo, telemetry: TelemetryData):
        """
        Add a channel to the plot.

        Args:
            channel: Channel metadata
            telemetry: Telemetry data object
        """
        if channel.name in self.plot_items:
            # Channel already plotted
            return

        self.telemetry = telemetry

        # Get channel data
        data_series = telemetry.get_channel_data(channel.name)
        if data_series is None:
            return

        # Get time data (index)
        time_data = data_series.index.to_numpy()
        values = data_series.to_numpy()

        # Remove NaN values for cleaner plotting
        mask = ~np.isnan(values)
        time_data = time_data[mask]
        values = values[mask]

        if len(time_data) == 0:
            return

        # Choose color (cycle through vibrant colors for dark backgrounds)
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
        color_idx = len(self.plot_items) % len(colors)
        color = colors[color_idx]

        # Add plot item
        pen = pg.mkPen(color=color, width=2)
        plot_item = self.plot_widget.plot(
            time_data,
            values,
            pen=pen,
            name=channel.name
        )

        # Store reference
        self.plot_items[channel.name] = {
            'plot_item': plot_item,
            'channel': channel,
            'color': color
        }

        # Auto-range to fit all data
        self._auto_scale()

    def _auto_scale(self):
        """
        Auto-scale the plot to fit all data.
        If 'Exclude Outliers' is checked, removes outliers on a per-channel basis before scaling.
        """
        if not self.plot_items:
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

                        # Define outlier bounds (1.5 * IQR is standard)
                        lower_bound = q1 - 1.5 * iqr
                        upper_bound = q3 + 1.5 * iqr

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

                # Auto-range X axis
                self.plot_widget.enableAutoRange(axis='x')
                return

        # If not excluding outliers or no data, just use standard auto-range
        self.plot_widget.autoRange()

    def remove_channel(self, channel_name: str):
        """
        Remove a channel from the plot.

        Args:
            channel_name: Name of the channel to remove
        """
        if channel_name not in self.plot_items:
            return

        # Remove plot item
        plot_info = self.plot_items[channel_name]
        self.plot_widget.removeItem(plot_info['plot_item'])

        # Remove from dict
        del self.plot_items[channel_name]

    def clear_all_plots(self):
        """Clear all plots."""
        # Remove all plot items
        for channel_name in list(self.plot_items.keys()):
            self.remove_channel(channel_name)

        # Clear the plot widget
        self.plot_widget.clear()
        self.plot_items.clear()

        # Re-add grid and legend with dark theme
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.legend = self.plot_widget.addLegend()
        self.legend.setBrush('#2d2d30')

        # Reinstall event filter for legend clicks
        self.legend.scene().installEventFilter(self)

    def dragEnterEvent(self, event):
        """Handle drag enter event."""
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        """Handle drag move event."""
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        """Handle drop event - add channel to plot."""
        if event.mimeData().hasText():
            # The text contains the channel name
            channel_name = event.mimeData().text()

            if self.telemetry:
                channel = self.telemetry.get_channel(channel_name)
                if channel:
                    self.add_channel(channel, self.telemetry)
                    event.acceptProposedAction()

    def _show_context_menu(self, position):
        """Show context menu for plot actions."""
        menu = QMenu(self)

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
