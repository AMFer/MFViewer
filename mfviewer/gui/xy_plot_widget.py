"""
XY Plot Widget for plotting one channel against another.
"""

from typing import Dict, List, Optional, Tuple
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QMenu, QPushButton
)
from PyQt6.QtCore import Qt, pyqtSignal, QEvent
from PyQt6.QtGui import QAction, QDragEnterEvent, QDropEvent
import pyqtgraph as pg
import numpy as np

from mfviewer.data.parser import ChannelInfo, TelemetryData


class DroppableComboBox(QComboBox):
    """ComboBox that accepts drag-and-drop of channel names."""

    channel_dropped = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        # Install event filter on the line edit (if editable) and the view
        self.view().setAcceptDrops(True)
        self.view().viewport().setAcceptDrops(True)
        self.view().viewport().installEventFilter(self)
        self.installEventFilter(self)

    def eventFilter(self, obj, event):
        """Handle drag events through event filter."""
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
                index = self.findText(channel_name)
                if index >= 0:
                    self.setCurrentIndex(index)
                event.acceptProposedAction()
                self.channel_dropped.emit(channel_name)
                return True
        return super().eventFilter(obj, event)

    def dragEnterEvent(self, event: QDragEnterEvent):
        """Accept drag if it contains text."""
        if event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        """Accept drag move if it contains text."""
        if event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        """Handle drop - set the channel name."""
        if event.mimeData().hasText():
            channel_name = event.mimeData().text()
            # Find and select the channel in the combo box
            index = self.findText(channel_name)
            if index >= 0:
                self.setCurrentIndex(index)
            event.acceptProposedAction()
            self.channel_dropped.emit(channel_name)
        else:
            event.ignore()


class XYPlotWidget(QWidget):
    """Widget for plotting one channel against another (X-Y scatter plot)."""

    def __init__(self, units_manager=None):
        super().__init__()
        self.telemetry: Optional[TelemetryData] = None
        self.units_manager = units_manager
        self.log_manager = None
        self.container = None
        self.remove_callback = None

        # Current channel selections
        self.x_channel: Optional[str] = None
        self.y_channel: Optional[str] = None

        # Cursor support - XY plots use crosshairs at the X/Y values corresponding to cursor time
        self.cursor_line = None  # Compatibility attribute (not used directly)
        self.cursor_active = False
        self.cursor_callback = None
        self.cursor_x_position = None  # Time position of cursor

        # Crosshair lines for XY plot
        self._crosshair_v = None  # Vertical line (X value)
        self._crosshair_h = None  # Horizontal line (Y value)

        # Plot data
        self.scatter_item = None

        # Store full data arrays for filtering
        self._time_data: Optional[np.ndarray] = None
        self._x_data: Optional[np.ndarray] = None
        self._y_data: Optional[np.ndarray] = None

        # Current time range filter (None = show all)
        self._time_range: Optional[Tuple[float, float]] = None

        self._setup_ui()

    def _setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        # Channel selection header
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(4, 2, 4, 2)
        header_layout.setSpacing(8)

        # X channel selector
        x_label = QLabel("X:")
        x_label.setStyleSheet("color: #cccccc; font-weight: bold;")
        header_layout.addWidget(x_label)

        self.x_combo = DroppableComboBox()
        self.x_combo.setMinimumWidth(150)
        self.x_combo.currentTextChanged.connect(self._on_x_changed)
        self.x_combo.installEventFilter(self)
        self.x_combo.setStyleSheet("""
            QComboBox {
                background-color: #3c3c3c;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 2px 6px;
            }
            QComboBox:hover {
                border-color: #007acc;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 4px solid #cccccc;
            }
            QComboBox QAbstractItemView {
                background-color: #252526;
                color: #ffffff;
                selection-background-color: #094771;
                border: 1px solid #3e3e42;
            }
        """)
        header_layout.addWidget(self.x_combo)

        # Y channel selector
        y_label = QLabel("Y:")
        y_label.setStyleSheet("color: #cccccc; font-weight: bold;")
        header_layout.addWidget(y_label)

        self.y_combo = DroppableComboBox()
        self.y_combo.setMinimumWidth(150)
        self.y_combo.currentTextChanged.connect(self._on_y_changed)
        self.y_combo.installEventFilter(self)
        self.y_combo.setStyleSheet(self.x_combo.styleSheet())
        header_layout.addWidget(self.y_combo)

        header_layout.addStretch()

        # Store header reference for drop target detection
        self.header = header
        self.header.setAcceptDrops(True)
        self.header.installEventFilter(self)
        layout.addWidget(header)

        # Enable drops on the XYPlotWidget itself
        self.setAcceptDrops(True)

        # Plot area
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('#1e1e1e')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)

        # Style the axes
        axis_pen = pg.mkPen(color='#888888', width=1)
        self.plot_widget.getAxis('bottom').setPen(axis_pen)
        self.plot_widget.getAxis('left').setPen(axis_pen)
        self.plot_widget.getAxis('bottom').setTextPen(pg.mkPen(color='#cccccc'))
        self.plot_widget.getAxis('left').setTextPen(pg.mkPen(color='#cccccc'))

        # Enable drag/drop on plot widget and install event filter
        self.plot_widget.setAcceptDrops(True)
        self.plot_widget.installEventFilter(self)

        layout.addWidget(self.plot_widget)

        # Enable context menu
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def eventFilter(self, obj, event):
        """Handle drag/drop events from child widgets."""
        # Guard against events before setup is complete
        if not hasattr(self, 'plot_widget'):
            return super().eventFilter(obj, event)

        # Handle events from plot_widget and header
        if obj in (self.plot_widget, self.header):
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
                    self._handle_channel_drop(channel_name, event.position().toPoint(), obj)
                    event.acceptProposedAction()
                    return True

        # Also handle events from combo boxes
        if obj in (self.x_combo, self.y_combo):
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
                    target_combo = obj
                    index = target_combo.findText(channel_name)
                    if index >= 0:
                        target_combo.setCurrentIndex(index)
                    event.acceptProposedAction()
                    return True

        return super().eventFilter(obj, event)

    def _handle_channel_drop(self, channel_name: str, drop_pos, source_widget):
        """Handle a channel drop, determining which combo to update."""
        # If dropped on header, check which combo box area
        if source_widget == self.header:
            # Map position to header coordinates
            x_rect = self.x_combo.geometry()
            y_rect = self.y_combo.geometry()

            if x_rect.contains(drop_pos):
                index = self.x_combo.findText(channel_name)
                if index >= 0:
                    self.x_combo.setCurrentIndex(index)
                return
            elif y_rect.contains(drop_pos):
                index = self.y_combo.findText(channel_name)
                if index >= 0:
                    self.y_combo.setCurrentIndex(index)
                return

        # Default behavior: fill X first, then Y
        if not self.x_channel:
            index = self.x_combo.findText(channel_name)
            if index >= 0:
                self.x_combo.setCurrentIndex(index)
        elif not self.y_channel:
            index = self.y_combo.findText(channel_name)
            if index >= 0:
                self.y_combo.setCurrentIndex(index)

    def dragEnterEvent(self, event: QDragEnterEvent):
        """Accept drag if it contains text."""
        if event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        """Accept drag move if it contains text."""
        if event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        """Handle drop - determine which combo box to update based on drop position."""
        if event.mimeData().hasText():
            channel_name = event.mimeData().text()
            drop_pos = event.position().toPoint()

            # Check if drop is over the X combo box area
            x_combo_rect = self.x_combo.geometry()
            x_combo_global = self.x_combo.parent().mapTo(self, x_combo_rect.topLeft())
            x_rect = x_combo_rect.translated(x_combo_global - x_combo_rect.topLeft())

            # Check if drop is over the Y combo box area
            y_combo_rect = self.y_combo.geometry()
            y_combo_global = self.y_combo.parent().mapTo(self, y_combo_rect.topLeft())
            y_rect = y_combo_rect.translated(y_combo_global - y_combo_rect.topLeft())

            if x_rect.contains(drop_pos):
                # Drop on X combo
                index = self.x_combo.findText(channel_name)
                if index >= 0:
                    self.x_combo.setCurrentIndex(index)
                event.acceptProposedAction()
            elif y_rect.contains(drop_pos):
                # Drop on Y combo
                index = self.y_combo.findText(channel_name)
                if index >= 0:
                    self.y_combo.setCurrentIndex(index)
                event.acceptProposedAction()
            else:
                # Drop elsewhere - default to X if empty, else Y if empty
                if not self.x_channel:
                    index = self.x_combo.findText(channel_name)
                    if index >= 0:
                        self.x_combo.setCurrentIndex(index)
                elif not self.y_channel:
                    index = self.y_combo.findText(channel_name)
                    if index >= 0:
                        self.y_combo.setCurrentIndex(index)
                event.acceptProposedAction()
        else:
            event.ignore()

    def set_telemetry(self, telemetry: TelemetryData):
        """Set the telemetry data and populate channel combos."""
        self.telemetry = telemetry
        self._populate_channel_combos()

    def _populate_channel_combos(self):
        """Populate the channel selection combo boxes."""
        self.x_combo.blockSignals(True)
        self.y_combo.blockSignals(True)

        self.x_combo.clear()
        self.y_combo.clear()

        if self.telemetry:
            channel_names = sorted(self.telemetry.get_channel_names())
            self.x_combo.addItems(channel_names)
            self.y_combo.addItems(channel_names)

        # Start with no selection (blank)
        self.x_combo.setCurrentIndex(-1)
        self.y_combo.setCurrentIndex(-1)

        self.x_combo.blockSignals(False)
        self.y_combo.blockSignals(False)

    def _on_x_changed(self, channel_name: str):
        """Handle X channel selection change."""
        self.x_channel = channel_name if channel_name else None
        self._update_plot()

    def _on_y_changed(self, channel_name: str):
        """Handle Y channel selection change."""
        self.y_channel = channel_name if channel_name else None
        self._update_plot()

    def _update_plot(self):
        """Update the scatter plot with current channel selections."""
        # Clear stored data
        self._time_data = None
        self._x_data = None
        self._y_data = None

        # Clear existing scatter
        if self.scatter_item:
            self.plot_widget.removeItem(self.scatter_item)
            self.scatter_item = None

        if not self.telemetry or not self.x_channel or not self.y_channel:
            return

        # Get channel info
        x_channel_info = self.telemetry.get_channel(self.x_channel)
        y_channel_info = self.telemetry.get_channel(self.y_channel)

        if x_channel_info is None or y_channel_info is None:
            return

        # Get channel data - support both real TelemetryData and mock objects
        if hasattr(self.telemetry, 'get_channel_data'):
            # Real TelemetryData - data is in DataFrame
            x_series = self.telemetry.get_channel_data(self.x_channel)
            y_series = self.telemetry.get_channel_data(self.y_channel)
            if x_series is None or y_series is None:
                return
            x_data = np.array(x_series.values, dtype=np.float32)
            y_data = np.array(y_series.values, dtype=np.float32)
            # Time is stored as the DataFrame index (Seconds) - should already be float
            try:
                time_data = np.array(x_series.index.values, dtype=np.float32)
            except (ValueError, TypeError):
                # Fallback if index is not numeric (shouldn't happen with proper parsing)
                time_data = None
        elif hasattr(x_channel_info, 'data'):
            # Mock object with data attribute
            x_data = np.array(x_channel_info.data, dtype=np.float32)
            y_data = np.array(y_channel_info.data, dtype=np.float32)
            time_data = None
        else:
            return

        # Get data type for unit conversion
        x_data_type = getattr(x_channel_info, 'data_type', 'float')
        y_data_type = getattr(y_channel_info, 'data_type', 'float')

        # Apply unit conversions if available
        if self.units_manager:
            x_data = self.units_manager.apply_channel_conversion(
                self.x_channel, x_data, x_data_type
            )
            y_data = self.units_manager.apply_channel_conversion(
                self.y_channel, y_data, y_data_type
            )

        # Remove NaN values
        valid_mask = ~(np.isnan(x_data) | np.isnan(y_data))
        if time_data is not None:
            valid_mask &= ~np.isnan(time_data)
            time_data = time_data[valid_mask]

        x_data = x_data[valid_mask]
        y_data = y_data[valid_mask]

        if len(x_data) == 0:
            return

        # Store full data for filtering
        self._time_data = time_data
        self._x_data = x_data
        self._y_data = y_data

        # Update axis labels
        x_unit = ""
        y_unit = ""
        if self.units_manager:
            x_unit = self.units_manager.get_unit(self.x_channel, channel_type=x_data_type)
            y_unit = self.units_manager.get_unit(self.y_channel, channel_type=y_data_type)

        x_label = f"{self.x_channel}"
        if x_unit:
            x_label += f" ({x_unit})"
        y_label = f"{self.y_channel}"
        if y_unit:
            y_label += f" ({y_unit})"

        self.plot_widget.setLabel('bottom', x_label, color='#cccccc')
        self.plot_widget.setLabel('left', y_label, color='#cccccc')

        # Draw the scatter plot with current time filter
        self._redraw_scatter()

    def _redraw_scatter(self):
        """Redraw scatter plot with current time range filter."""
        # Clear existing scatter
        if self.scatter_item:
            self.plot_widget.removeItem(self.scatter_item)
            self.scatter_item = None

        if self._x_data is None or self._y_data is None:
            return

        # Apply time range filter if we have time data and a filter
        if self._time_data is not None and self._time_range is not None:
            t_min, t_max = self._time_range
            mask = (self._time_data >= t_min) & (self._time_data <= t_max)
            x_filtered = self._x_data[mask]
            y_filtered = self._y_data[mask]
        else:
            x_filtered = self._x_data
            y_filtered = self._y_data

        if len(x_filtered) == 0:
            return

        # Create scatter plot
        self.scatter_item = pg.ScatterPlotItem(
            x=x_filtered, y=y_filtered,
            pen=None,
            brush=pg.mkBrush(100, 150, 255, 120),
            size=5
        )
        self.plot_widget.addItem(self.scatter_item)

        # Auto-range to show all filtered data
        self.plot_widget.autoRange()

    def set_time_range(self, t_min: float, t_max: float):
        """Set the time range filter for the scatter plot.

        Only points whose corresponding time values fall within [t_min, t_max]
        will be displayed. This allows the XY plot to sync with the visible
        range of time-series plots.

        Args:
            t_min: Minimum time value
            t_max: Maximum time value
        """
        self._time_range = (t_min, t_max)
        self._redraw_scatter()

    def clear_time_range(self):
        """Clear the time range filter, showing all data points."""
        self._time_range = None
        self._redraw_scatter()

    def get_y_axis_width(self) -> int:
        """Get the current width of the Y-axis in pixels.

        Returns:
            Width of the Y-axis area in pixels
        """
        y_axis = self.plot_widget.getAxis('left')
        return y_axis.width() if y_axis else 0

    def set_y_axis_width(self, width: int):
        """Set a fixed width for the Y-axis.

        Args:
            width: Width in pixels for the Y-axis
        """
        y_axis = self.plot_widget.getAxis('left')
        if y_axis:
            y_axis.setWidth(width)

    def _show_context_menu(self, position):
        """Show context menu for plot actions."""
        menu = QMenu(self)

        # Add plot action (if container supports it)
        if self.container and hasattr(self.container, 'add_plot'):
            add_plot_action = QAction("Add Plot", self)
            add_plot_action.triggered.connect(self.container.add_plot)
            menu.addAction(add_plot_action)

        # Convert to time-series plot
        if self.container and hasattr(self.container, 'convert_to_time_plot'):
            convert_action = QAction("Convert to Time Plot", self)
            convert_action.triggered.connect(lambda: self.container.convert_to_time_plot(self))
            menu.addAction(convert_action)

        menu.addSeparator()

        # Auto scale
        auto_scale_action = QAction("Auto Scale", self)
        auto_scale_action.triggered.connect(lambda: self.plot_widget.autoRange())
        menu.addAction(auto_scale_action)

        # Clear plot
        clear_action = QAction("Clear Plot", self)
        clear_action.triggered.connect(self._clear_plot)
        menu.addAction(clear_action)

        # Remove plot action
        if self.remove_callback:
            menu.addSeparator()
            remove_action = QAction("Remove This Plot", self)
            remove_action.triggered.connect(lambda: self.remove_callback(self))
            menu.addAction(remove_action)

        menu.exec(self.mapToGlobal(position))

    def _clear_plot(self):
        """Clear the plot and reset channel selections."""
        if self.scatter_item:
            self.plot_widget.removeItem(self.scatter_item)
            self.scatter_item = None

        # Remove crosshairs
        if self._crosshair_v is not None:
            self.plot_widget.removeItem(self._crosshair_v)
            self._crosshair_v = None
        if self._crosshair_h is not None:
            self.plot_widget.removeItem(self._crosshair_h)
            self._crosshair_h = None

        self.x_combo.setCurrentIndex(-1)
        self.y_combo.setCurrentIndex(-1)
        self.x_channel = None
        self.y_channel = None

    def clear_all_plots(self):
        """Clear the plot (compatibility with PlotWidget interface)."""
        self._clear_plot()

    def get_channel_names(self) -> List[str]:
        """Get list of channel names used in this plot (compatibility with PlotWidget interface)."""
        channels = []
        if self.x_channel:
            channels.append(self.x_channel)
        if self.y_channel:
            channels.append(self.y_channel)
        return channels

    def get_y_range(self) -> Optional[Tuple[float, float]]:
        """Get Y-axis range (compatibility with PlotWidget interface)."""
        view_range = self.plot_widget.viewRange()
        if view_range:
            return (view_range[1][0], view_range[1][1])
        return None

    def get_configuration(self) -> dict:
        """Get current configuration for saving."""
        return {
            'type': 'xy_plot',
            'x_channel': self.x_channel,
            'y_channel': self.y_channel
        }

    def load_configuration(self, config: dict):
        """Load configuration from saved state."""
        if config.get('type') != 'xy_plot':
            return

        x_channel = config.get('x_channel')
        y_channel = config.get('y_channel')

        if x_channel and self.x_combo.findText(x_channel) >= 0:
            self.x_combo.setCurrentText(x_channel)

        if y_channel and self.y_combo.findText(y_channel) >= 0:
            self.y_combo.setCurrentText(y_channel)

    def refresh_data(self, new_telemetry: TelemetryData = None):
        """Refresh plot with new telemetry data."""
        if new_telemetry:
            self.telemetry = new_telemetry
            self._populate_channel_combos()

            # Restore selections if they exist in new data
            if self.x_channel and self.x_combo.findText(self.x_channel) >= 0:
                self.x_combo.setCurrentText(self.x_channel)
            if self.y_channel and self.y_combo.findText(self.y_channel) >= 0:
                self.y_combo.setCurrentText(self.y_channel)

        self._update_plot()

    def set_cursor_position(self, time_pos: float, defer_repaint: bool = False):
        """Set cursor position and show crosshairs at corresponding X/Y values.

        For XY plots, the cursor position is a time value. We find the X and Y
        channel values at that time and display crosshairs at that point.

        Note: defer_repaint is accepted for API compatibility but XY plots always
        update their crosshairs immediately since they use PyQtGraph's InfiniteLine
        which is efficient and doesn't have the same repaint overhead as overlays.

        Args:
            time_pos: Time position to show cursor at
            defer_repaint: Accepted for API compatibility (ignored for XY plots)
        """
        self.cursor_x_position = time_pos
        self.cursor_active = True

        # Need time data and channel data to show crosshairs
        if self._time_data is None or self._x_data is None or self._y_data is None:
            self._hide_crosshairs()
            return

        if len(self._time_data) == 0:
            self._hide_crosshairs()
            return

        # Find X and Y values at the given time position using interpolation
        x_val, y_val = self._interpolate_at_time(time_pos)

        if x_val is None or y_val is None:
            self._hide_crosshairs()
            return

        # Show crosshairs at the interpolated X/Y position
        # XY plots always show crosshairs regardless of defer_repaint since
        # InfiniteLine is lightweight and doesn't trigger full plot repaints
        self._show_crosshairs(x_val, y_val)

    def _interpolate_at_time(self, time_pos: float) -> Tuple[Optional[float], Optional[float]]:
        """Interpolate X and Y channel values at a given time position.

        Args:
            time_pos: Time position to interpolate at

        Returns:
            Tuple of (x_value, y_value) or (None, None) if outside data range
        """
        if self._time_data is None or len(self._time_data) == 0:
            return None, None

        time_data = self._time_data
        x_data = self._x_data
        y_data = self._y_data

        # Handle boundary cases
        if time_pos <= time_data[0]:
            return float(x_data[0]), float(y_data[0])
        elif time_pos >= time_data[-1]:
            return float(x_data[-1]), float(y_data[-1])

        # Find insertion point for interpolation
        idx = np.searchsorted(time_data, time_pos)

        if idx == 0:
            return float(x_data[0]), float(y_data[0])
        elif idx >= len(time_data):
            return float(x_data[-1]), float(y_data[-1])

        # Linear interpolation
        t0, t1 = time_data[idx - 1], time_data[idx]
        if t1 == t0:
            return float(x_data[idx - 1]), float(y_data[idx - 1])

        # Interpolation factor
        t = (time_pos - t0) / (t1 - t0)

        x_val = x_data[idx - 1] + t * (x_data[idx] - x_data[idx - 1])
        y_val = y_data[idx - 1] + t * (y_data[idx] - y_data[idx - 1])

        return float(x_val), float(y_val)

    def _show_crosshairs(self, x_val: float, y_val: float):
        """Show crosshairs at the given X/Y position.

        Args:
            x_val: X-axis value for vertical line
            y_val: Y-axis value for horizontal line
        """
        # Create crosshair lines if they don't exist
        if self._crosshair_v is None:
            self._crosshair_v = pg.InfiniteLine(
                angle=90,  # Vertical
                pen=pg.mkPen(color=(255, 255, 0), width=1)
            )
            self.plot_widget.addItem(self._crosshair_v)

        if self._crosshair_h is None:
            self._crosshair_h = pg.InfiniteLine(
                angle=0,  # Horizontal
                pen=pg.mkPen(color=(255, 255, 0), width=1)
            )
            self.plot_widget.addItem(self._crosshair_h)

        # Update positions
        self._crosshair_v.setPos(x_val)
        self._crosshair_h.setPos(y_val)

        # Show them
        self._crosshair_v.setVisible(True)
        self._crosshair_h.setVisible(True)

    def _hide_crosshairs(self):
        """Hide the crosshair lines."""
        if self._crosshair_v is not None:
            self._crosshair_v.setVisible(False)
        if self._crosshair_h is not None:
            self._crosshair_h.setVisible(False)
