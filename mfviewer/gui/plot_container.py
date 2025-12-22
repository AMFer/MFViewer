"""
Container widget for managing multiple tiled plot widgets in a tab.
"""

from typing import List, Dict, Any
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QSplitter, QToolButton, QMenu, QCheckBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction

from mfviewer.gui.plot_widget import PlotWidget
from mfviewer.data.parser import ChannelInfo, TelemetryData


class PlotContainer(QWidget):
    """Container widget that holds multiple tiled plot widgets."""

    def __init__(self, sync_callback=None):
        super().__init__()
        self.plot_widgets: List[PlotWidget] = []
        self.telemetry: TelemetryData = None
        self.sync_callback = sync_callback  # Callback to sync all plots globally
        self._setup_ui()

    def _setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar for managing plots
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setContentsMargins(5, 5, 5, 5)

        # Add plot button
        self.add_plot_btn = QPushButton("Add Plot")
        self.add_plot_btn.setStyleSheet("""
            QPushButton {
                background-color: #0e639c;
                color: #ffffff;
                border: none;
                padding: 5px 15px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
            QPushButton:pressed {
                background-color: #0d5a8f;
            }
        """)
        self.add_plot_btn.clicked.connect(self._add_plot)
        toolbar_layout.addWidget(self.add_plot_btn)
        toolbar_layout.addSpacing(10)

        # Layout direction buttons
        self.layout_horizontal_btn = QPushButton("Horizontal")
        self.layout_horizontal_btn.setStyleSheet("""
            QPushButton {
                background-color: #0e639c;
                color: #ffffff;
                border: none;
                padding: 5px 15px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
            QPushButton:pressed {
                background-color: #0d5a8f;
            }
        """)
        self.layout_horizontal_btn.clicked.connect(lambda: self._set_layout_orientation(Qt.Orientation.Horizontal))
        toolbar_layout.addWidget(self.layout_horizontal_btn)

        self.layout_vertical_btn = QPushButton("Vertical")
        self.layout_vertical_btn.setStyleSheet("""
            QPushButton {
                background-color: #0e639c;
                color: #ffffff;
                border: none;
                padding: 5px 15px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
            QPushButton:pressed {
                background-color: #0d5a8f;
            }
        """)
        self.layout_vertical_btn.clicked.connect(lambda: self._set_layout_orientation(Qt.Orientation.Vertical))
        toolbar_layout.addWidget(self.layout_vertical_btn)
        toolbar_layout.addSpacing(10)

        # Auto scale button
        self.auto_scale_btn = QPushButton("Auto Scale")
        self.auto_scale_btn.setStyleSheet("""
            QPushButton {
                background-color: #0e639c;
                color: #ffffff;
                border: none;
                padding: 5px 15px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
            QPushButton:pressed {
                background-color: #0d5a8f;
            }
        """)
        self.auto_scale_btn.clicked.connect(self._auto_scale_all)
        toolbar_layout.addWidget(self.auto_scale_btn)
        toolbar_layout.addSpacing(10)

        # Exclude outliers checkbox (checked by default)
        self.exclude_outliers_cb = QCheckBox("Exclude Outliers")
        self.exclude_outliers_cb.setChecked(True)
        self.exclude_outliers_cb.setStyleSheet("""
            QCheckBox {
                color: #dcdcdc;
                spacing: 5px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid #3e3e42;
                border-radius: 3px;
                background-color: #2d2d30;
            }
            QCheckBox::indicator:checked {
                background-color: #0e639c;
                border-color: #0e639c;
            }
        """)
        self.exclude_outliers_cb.stateChanged.connect(self._on_exclude_outliers_changed)
        toolbar_layout.addWidget(self.exclude_outliers_cb)

        toolbar_layout.addStretch()
        layout.addLayout(toolbar_layout)

        # Splitter to hold plot widgets
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #3e3e42;
            }
            QSplitter::handle:hover {
                background-color: #007acc;
            }
        """)
        layout.addWidget(self.splitter)

        # Add initial plot
        self._add_plot()

    def _add_plot(self):
        """Add a new plot widget to the container."""
        plot_widget = PlotWidget()

        # If we have telemetry data, set it on the new plot
        if self.telemetry:
            plot_widget.telemetry = self.telemetry

        # Apply current exclude outliers setting
        plot_widget.exclude_outliers = self.exclude_outliers_cb.isChecked()

        # Set remove callback
        plot_widget.remove_callback = self._remove_plot

        # Set cursor callback for synchronization
        # Use global sync if available, otherwise use local sync
        if hasattr(self, '_global_cursor_sync'):
            plot_widget.cursor_callback = self._global_cursor_sync
        else:
            plot_widget.cursor_callback = self._on_cursor_moved

        self.plot_widgets.append(plot_widget)
        self.splitter.addWidget(plot_widget)

        # Distribute space evenly
        sizes = [100] * len(self.plot_widgets)
        self.splitter.setSizes(sizes)

        # Synchronize X-axis globally if callback is available
        if self.sync_callback:
            self.sync_callback()

    def _remove_plot(self, plot_widget: PlotWidget):
        """Remove a plot widget from the container."""
        if len(self.plot_widgets) <= 1:
            # Don't remove the last plot
            return

        if plot_widget in self.plot_widgets:
            self.plot_widgets.remove(plot_widget)
            plot_widget.setParent(None)
            plot_widget.deleteLater()

    def _set_layout_orientation(self, orientation: Qt.Orientation):
        """Set the layout orientation (horizontal or vertical tiling)."""
        self.splitter.setOrientation(orientation)

    def _auto_scale_all(self):
        """Auto-scale all plots in this container."""
        for plot_widget in self.plot_widgets:
            plot_widget._auto_scale()

    def _on_exclude_outliers_changed(self, state):
        """Handle exclude outliers checkbox state change."""
        exclude = self.exclude_outliers_cb.isChecked()
        for plot_widget in self.plot_widgets:
            plot_widget.exclude_outliers = exclude

    def add_channel_to_active_plot(self, channel: ChannelInfo, telemetry: TelemetryData):
        """
        Add a channel to the currently focused plot widget.

        Args:
            channel: Channel metadata
            telemetry: Telemetry data object
        """
        self.telemetry = telemetry

        # Find the focused plot widget, or use the last one
        focused_plot = None
        for plot in self.plot_widgets:
            if plot.hasFocus() or plot.underMouse():
                focused_plot = plot
                break

        # If no focused plot, use the last one
        if not focused_plot and self.plot_widgets:
            focused_plot = self.plot_widgets[-1]

        if focused_plot:
            focused_plot.add_channel(channel, telemetry)

    def get_all_plot_widgets(self) -> List[PlotWidget]:
        """Get all plot widgets in this container."""
        return self.plot_widgets

    def get_configuration(self) -> Dict[str, Any]:
        """
        Get the configuration for all plots in this container.

        Returns:
            Dictionary containing plot configurations
        """
        return {
            'orientation': 'horizontal' if self.splitter.orientation() == Qt.Orientation.Horizontal else 'vertical',
            'plots': [
                {
                    'channels': plot.get_channel_names()
                }
                for plot in self.plot_widgets
            ]
        }

    def load_configuration(self, config: Dict[str, Any], telemetry: TelemetryData):
        """
        Load configuration into the container.

        Args:
            config: Configuration dictionary
            telemetry: Telemetry data object
        """
        self.telemetry = telemetry

        # Clear existing plots (force clear all, even the last one)
        for plot in self.plot_widgets[:]:
            self.plot_widgets.remove(plot)
            plot.setParent(None)
            plot.deleteLater()

        # Set orientation
        orientation = Qt.Orientation.Horizontal if config.get('orientation', 'horizontal') == 'horizontal' else Qt.Orientation.Vertical
        self.splitter.setOrientation(orientation)

        # Add plots
        plots_config = config.get('plots', [])
        if not plots_config:
            # If no plots in config, add one default plot
            self._add_plot()
        else:
            for plot_config in plots_config:
                self._add_plot()
                plot_widget = self.plot_widgets[-1]

                # Add channels
                for channel_name in plot_config.get('channels', []):
                    channel = telemetry.get_channel(channel_name)
                    if channel:
                        plot_widget.add_channel(channel, telemetry)

    def clear_all_plots(self):
        """Clear all data from all plot widgets."""
        for plot in self.plot_widgets:
            plot.clear_all_plots()

    def _on_cursor_moved(self, x_pos: float):
        """
        Handle cursor movement from one plot and synchronize to others.

        Args:
            x_pos: X position of the cursor
        """
        # Update cursor position in all plots in this container
        for plot in self.plot_widgets:
            # Temporarily disable cursor callback to avoid infinite recursion
            original_callback = plot.cursor_callback
            plot.cursor_callback = None
            plot.set_cursor_position(x_pos)
            plot.cursor_callback = original_callback

        # Also notify global sync callback if available
        if self.sync_callback:
            # The sync_callback is for X-axis linking, we'd need a separate one for cursor
            pass
