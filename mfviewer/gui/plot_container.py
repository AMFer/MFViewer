"""
Container widget for managing multiple tiled plot widgets in a tab.
"""

from typing import List, Dict, Any
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QSplitter
from PyQt6.QtCore import Qt

from mfviewer.gui.plot_widget import PlotWidget
from mfviewer.data.parser import ChannelInfo, TelemetryData


class PlotContainer(QWidget):
    """Container widget that holds multiple tiled plot widgets."""

    def __init__(self, sync_callback=None, units_manager=None):
        super().__init__()
        self.plot_widgets: List[PlotWidget] = []
        self.telemetry: TelemetryData = None
        self.sync_callback = sync_callback  # Callback to sync all plots globally
        self.units_manager = units_manager  # Units manager for conversions
        self._setup_ui()

    def _setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Splitter to hold plot widgets (toolbar removed - all actions moved to context menu)
        # Default to vertical layout (stacked plots)
        self.splitter = QSplitter(Qt.Orientation.Vertical)
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

    def add_plot(self):
        """Add a new plot widget to the container (public method for context menu)."""
        self._add_plot()

    def _add_plot(self):
        """Add a new plot widget to the container."""
        plot_widget = PlotWidget(units_manager=self.units_manager)

        # If we have telemetry data, set it on the new plot
        if self.telemetry:
            plot_widget.telemetry = self.telemetry

        # Default exclude outliers to True
        plot_widget.exclude_outliers = True

        # Set remove callback
        plot_widget.remove_callback = self._remove_plot

        # Set container reference for context menu access
        plot_widget.container = self

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

    def set_layout_orientation(self, orientation: Qt.Orientation):
        """Set the layout orientation (horizontal or vertical tiling) - public method for context menu."""
        self.splitter.setOrientation(orientation)
        # Re-synchronize X-axes after layout change
        if self.sync_callback:
            self.sync_callback()

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
        plots_config = []
        for plot in self.plot_widgets:
            plot_config = {
                'channels': plot.get_channel_names()
            }
            # Include Y-axis range if available
            y_range = plot.get_y_range()
            if y_range:
                plot_config['y_range'] = list(y_range)
            plots_config.append(plot_config)

        return {
            'orientation': 'horizontal' if self.splitter.orientation() == Qt.Orientation.Horizontal else 'vertical',
            'plots': plots_config
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

                # Restore Y-axis range if saved
                y_range = plot_config.get('y_range')
                if y_range and len(y_range) >= 2:
                    plot_widget.set_y_range(y_range[0], y_range[1])

    def refresh_with_new_telemetry(self, new_telemetry: TelemetryData):
        """
        Refresh all plot widgets with new telemetry data.
        This is called when a new log file is loaded.

        Args:
            new_telemetry: New telemetry data object
        """
        self.telemetry = new_telemetry
        for plot in self.plot_widgets:
            plot.refresh_with_new_telemetry(new_telemetry)

    def clear_all_plots(self):
        """Clear all data from all plot widgets."""
        for plot in self.plot_widgets:
            plot.clear_all_plots()

    def refresh_with_new_units(self):
        """Refresh all plot widgets with new unit conversions."""
        for plot in self.plot_widgets:
            plot.refresh_with_new_units()

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
