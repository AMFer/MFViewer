"""
Main application window.
"""

from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTabWidget, QFileDialog, QMessageBox,
    QStatusBar, QToolBar, QTreeWidget, QTreeWidgetItem,
    QLabel, QPushButton, QInputDialog, QMenu, QDialog
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QAction, QKeySequence, QPalette, QColor, QCloseEvent

from mfviewer.data.parser import MFLogParser, TelemetryData
from mfviewer.gui.plot_widget import PlotWidget
from mfviewer.gui.plot_container import PlotContainer
from mfviewer.gui.preferences_dialog import PreferencesDialog
from mfviewer.utils.config import TabConfiguration
from mfviewer.utils.units import UnitsManager


class ChannelTreeWidget(QTreeWidget):
    """Custom QTreeWidget that supports drag-and-drop of channel data."""

    def startDrag(self, supportedActions):
        """Start drag operation with channel name as mime data."""
        item = self.currentItem()
        if item:
            channel = item.data(0, Qt.ItemDataRole.UserRole)
            if channel:
                # Create drag object with channel name
                from PyQt6.QtCore import QMimeData, QByteArray
                from PyQt6.QtGui import QDrag

                drag = QDrag(self)
                mime_data = QMimeData()
                mime_data.setText(channel.name)
                drag.setMimeData(mime_data)
                drag.exec(Qt.DropAction.CopyAction)
            else:
                # Not a channel item (probably a group), don't allow drag
                return
        else:
            super().startDrag(supportedActions)


class MainWindow(QMainWindow):
    """Main application window for MFViewer."""

    def __init__(self):
        super().__init__()
        self.telemetry: Optional[TelemetryData] = None
        self.current_file: Optional[Path] = None
        self.plot_tabs: list = []  # Track all plot tab widgets
        self.tab_counter: int = 1  # Counter for naming new tabs
        self.master_viewbox = None  # Master viewbox for X-axis synchronization

        # Initialize units manager
        self.units_manager = UnitsManager()
        self._load_unit_preferences()

        self.setWindowTitle("MFViewer - Motorsports Fusion Telemetry Viewer")
        self.setMinimumSize(1200, 800)

        self._apply_dark_theme()
        self._setup_ui()
        self._setup_menus()
        self._setup_toolbar()
        self._setup_statusbar()
        self._restore_session()

    def _apply_dark_theme(self):
        """Apply dark theme to the application."""
        palette = QPalette()

        # Define dark theme colors
        dark_bg = QColor(45, 45, 48)
        darker_bg = QColor(30, 30, 30)
        darkest_bg = QColor(25, 25, 28)
        text_color = QColor(220, 220, 220)
        disabled_text = QColor(127, 127, 127)
        highlight_color = QColor(42, 130, 218)
        highlight_text = QColor(255, 255, 255)

        # Set palette colors
        palette.setColor(QPalette.ColorRole.Window, dark_bg)
        palette.setColor(QPalette.ColorRole.WindowText, text_color)
        palette.setColor(QPalette.ColorRole.Base, darkest_bg)
        palette.setColor(QPalette.ColorRole.AlternateBase, darker_bg)
        palette.setColor(QPalette.ColorRole.ToolTipBase, darkest_bg)
        palette.setColor(QPalette.ColorRole.ToolTipText, text_color)
        palette.setColor(QPalette.ColorRole.Text, text_color)
        palette.setColor(QPalette.ColorRole.Button, darker_bg)
        palette.setColor(QPalette.ColorRole.ButtonText, text_color)
        palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
        palette.setColor(QPalette.ColorRole.Link, highlight_color)
        palette.setColor(QPalette.ColorRole.Highlight, highlight_color)
        palette.setColor(QPalette.ColorRole.HighlightedText, highlight_text)

        # Disabled colors
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, disabled_text)
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, disabled_text)
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, disabled_text)

        self.setPalette(palette)

        # Additional stylesheet for fine-tuning
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2d2d30;
            }
            QMenuBar {
                background-color: #2d2d30;
                color: #dcdcdc;
                border-bottom: 1px solid #3e3e42;
            }
            QMenuBar::item:selected {
                background-color: #3e3e42;
            }
            QMenu {
                background-color: #2d2d30;
                color: #dcdcdc;
                border: 1px solid #3e3e42;
            }
            QMenu::item:selected {
                background-color: #2a82da;
            }
            QToolBar {
                background-color: #2d2d30;
                border-bottom: 1px solid #3e3e42;
                spacing: 3px;
            }
            QToolBar QToolButton {
                background-color: #0e639c;
                color: #ffffff;
                border: 1px solid #0e639c;
                padding: 6px 12px;
                border-radius: 2px;
                margin: 2px;
            }
            QToolBar QToolButton:hover {
                background-color: #1177bb;
                border: 1px solid #1177bb;
            }
            QToolBar QToolButton:pressed {
                background-color: #007acc;
            }
            QStatusBar {
                background-color: #007acc;
                color: #ffffff;
            }
            QTreeWidget {
                background-color: #1e1e1e;
                color: #dcdcdc;
                border: 1px solid #3e3e42;
            }
            QTreeWidget::item:selected {
                background-color: #2a82da;
            }
            QTreeWidget::item:hover {
                background-color: #3e3e42;
            }
            QTabWidget::pane {
                border: 1px solid #3e3e42;
                background-color: #2d2d30;
            }
            QTabBar::tab {
                background-color: #2d2d30;
                color: #dcdcdc;
                padding: 8px 16px;
                border: 1px solid #3e3e42;
                border-bottom: none;
            }
            QTabBar::tab:selected {
                background-color: #1e1e1e;
                border-bottom: 2px solid #007acc;
            }
            QTabBar::tab:hover {
                background-color: #3e3e42;
            }
            QLabel {
                color: #dcdcdc;
            }
            QPushButton {
                background-color: #0e639c;
                color: #ffffff;
                border: 1px solid #0e639c;
                padding: 6px 12px;
                border-radius: 2px;
            }
            QPushButton:hover {
                background-color: #1177bb;
                border: 1px solid #1177bb;
            }
            QPushButton:pressed {
                background-color: #007acc;
            }
            QPushButton:disabled {
                background-color: #3e3e42;
                color: #7f7f7f;
                border: 1px solid #3e3e42;
            }
            QListWidget {
                background-color: #1e1e1e;
                color: #dcdcdc;
                border: 1px solid #3e3e42;
            }
            QListWidget::item:selected {
                background-color: #2a82da;
            }
            QListWidget::item:hover {
                background-color: #3e3e42;
            }
            QSplitter::handle {
                background-color: #3e3e42;
            }
            QMessageBox {
                background-color: #1e1e1e;
            }
            QMessageBox QLabel {
                color: #dcdcdc;
            }
            QFileDialog {
                background-color: #1e1e1e;
                color: #dcdcdc;
            }
            QFileDialog QTreeView {
                background-color: #252526;
                color: #dcdcdc;
                border: 1px solid #3e3e42;
            }
            QFileDialog QListView {
                background-color: #252526;
                color: #dcdcdc;
                border: 1px solid #3e3e42;
            }
            QFileDialog QLineEdit {
                background-color: #3c3c3c;
                color: #dcdcdc;
                border: 1px solid #3e3e42;
                padding: 4px;
            }
        """)

    def _setup_ui(self):
        """Set up the user interface layout."""
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main layout
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)

        # Create splitter for resizable panels
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel: Channel selector
        self.channel_tree = ChannelTreeWidget()
        self.channel_tree.setHeaderLabel("Channels")
        self.channel_tree.setMinimumWidth(200)
        self.channel_tree.setMaximumWidth(400)
        self.channel_tree.itemDoubleClicked.connect(self._on_channel_double_clicked)

        # Enable drag and drop
        self.channel_tree.setDragEnabled(True)
        self.channel_tree.setDragDropMode(ChannelTreeWidget.DragDropMode.DragOnly)

        self.splitter.addWidget(self.channel_tree)

        # Center panel: Tab widget for different views
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self._close_tab)

        # Enable context menu on tabs
        self.tab_widget.tabBar().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tab_widget.tabBar().customContextMenuRequested.connect(self._show_tab_context_menu)

        # Add "+" button for new tabs
        self.new_tab_button = QPushButton("+")
        self.new_tab_button.setMaximumSize(30, 30)
        self.new_tab_button.setToolTip("Create new plot tab")
        self.new_tab_button.clicked.connect(self._create_new_plot_tab)
        self.tab_widget.setCornerWidget(self.new_tab_button, Qt.Corner.TopRightCorner)

        # Create first plot tab
        self._create_new_plot_tab()

        self.splitter.addWidget(self.tab_widget)

        # Set initial splitter sizes (20% left, 80% right)
        self.splitter.setSizes([250, 950])

        main_layout.addWidget(self.splitter)

    def _setup_menus(self):
        """Set up the menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        open_action = QAction("&Open...", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.open_file_dialog)
        file_menu.addAction(open_action)

        file_menu.addSeparator()

        # Configuration save/load
        save_config_action = QAction("&Save Tab Configuration...", self)
        save_config_action.setShortcut(QKeySequence("Ctrl+S"))
        save_config_action.triggered.connect(self._save_configuration)
        file_menu.addAction(save_config_action)

        load_config_action = QAction("&Load Tab Configuration...", self)
        load_config_action.setShortcut(QKeySequence("Ctrl+L"))
        load_config_action.triggered.connect(self._load_configuration)
        file_menu.addAction(load_config_action)

        file_menu.addSeparator()

        export_action = QAction("&Export Data...", self)
        export_action.setEnabled(False)  # Enable when file is loaded
        file_menu.addAction(export_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # View menu
        view_menu = menubar.addMenu("&View")

        # Tab management
        new_tab_action = QAction("&New Plot Tab", self)
        new_tab_action.setShortcut(QKeySequence("Ctrl+T"))
        new_tab_action.triggered.connect(self._create_new_plot_tab)
        view_menu.addAction(new_tab_action)

        close_tab_action = QAction("&Close Current Tab", self)
        close_tab_action.setShortcut(QKeySequence("Ctrl+W"))
        close_tab_action.triggered.connect(lambda: self._close_tab(self.tab_widget.currentIndex()))
        view_menu.addAction(close_tab_action)

        rename_tab_action = QAction("&Rename Tab", self)
        rename_tab_action.setShortcut(QKeySequence("F2"))
        rename_tab_action.triggered.connect(lambda: self._rename_tab(self.tab_widget.currentIndex()))
        view_menu.addAction(rename_tab_action)

        view_menu.addSeparator()

        zoom_in_action = QAction("Zoom &In", self)
        zoom_in_action.setShortcut(QKeySequence.StandardKey.ZoomIn)
        view_menu.addAction(zoom_in_action)

        zoom_out_action = QAction("Zoom &Out", self)
        zoom_out_action.setShortcut(QKeySequence.StandardKey.ZoomOut)
        view_menu.addAction(zoom_out_action)

        reset_zoom_action = QAction("&Reset Zoom", self)
        reset_zoom_action.setShortcut(QKeySequence("Ctrl+0"))
        view_menu.addAction(reset_zoom_action)

        # Tools menu
        tools_menu = menubar.addMenu("&Tools")

        preferences_action = QAction("&Preferences...", self)
        preferences_action.setShortcut(QKeySequence("Ctrl+,"))
        preferences_action.triggered.connect(self._show_preferences)
        tools_menu.addAction(preferences_action)

        # Help menu
        help_menu = menubar.addMenu("&Help")

        about_action = QAction("&About MFViewer", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_toolbar(self):
        """Set up the toolbar."""
        toolbar = QToolBar("Main Toolbar")
        toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(toolbar)

        open_action = QAction("Open", self)
        open_action.triggered.connect(self.open_file_dialog)
        toolbar.addAction(open_action)

        toolbar.addSeparator()

        new_tab_action = QAction("New Tab", self)
        new_tab_action.setToolTip("Create new plot tab (Ctrl+T)")
        new_tab_action.triggered.connect(self._create_new_plot_tab)
        toolbar.addAction(new_tab_action)

    def _setup_statusbar(self):
        """Set up the status bar."""
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        self.statusbar.showMessage("Ready")

    def open_file_dialog(self):
        """Open file dialog to select a log file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Telemetry Log File",
            "",
            "CSV Files (*.csv);;All Files (*.*)"
        )

        if file_path:
            self.open_file(file_path)

    def open_file(self, file_path: str):
        """
        Open and parse a telemetry log file.

        Args:
            file_path: Path to the log file
        """
        try:
            self.statusbar.showMessage(f"Loading {Path(file_path).name}...")
            self.current_file = Path(file_path)

            # Parse the file
            parser = MFLogParser(file_path)
            self.telemetry = parser.parse()

            # Update UI
            self._populate_channel_tree()
            self._update_window_title()

            # Update all plot widgets with telemetry data for drag-and-drop
            for i in range(self.tab_widget.count()):
                widget = self.tab_widget.widget(i)
                if isinstance(widget, PlotContainer):
                    widget.telemetry = self.telemetry
                    for plot_widget in widget.get_all_plot_widgets():
                        plot_widget.telemetry = self.telemetry
                elif isinstance(widget, PlotWidget):
                    widget.telemetry = self.telemetry

            # Update status bar
            time_range = self.telemetry.get_time_range()
            duration = time_range[1] - time_range[0]
            self.statusbar.showMessage(
                f"Loaded: {len(self.telemetry.channels)} channels, "
                f"{len(self.telemetry.data)} samples, "
                f"{duration:.1f}s duration"
            )

        except Exception as e:
            QMessageBox.critical(
                self,
                "Error Loading File",
                f"Failed to load file:\n{str(e)}"
            )
            self.statusbar.showMessage("Failed to load file")

    def _populate_channel_tree(self):
        """Populate the channel tree with available channels."""
        self.channel_tree.clear()

        if not self.telemetry:
            return

        # Group channels by type
        type_groups = {}
        for channel in self.telemetry.channels:
            if channel.data_type not in type_groups:
                type_groups[channel.data_type] = []
            type_groups[channel.data_type].append(channel)

        # Add to tree
        for data_type in sorted(type_groups.keys()):
            # Create group item
            group_item = QTreeWidgetItem(self.channel_tree, [data_type])
            group_item.setExpanded(False)

            # Add channels to group
            for channel in sorted(type_groups[data_type], key=lambda c: c.name):
                channel_item = QTreeWidgetItem(group_item, [channel.name])
                channel_item.setData(0, Qt.ItemDataRole.UserRole, channel)

    def _on_channel_double_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle double-click on channel item."""
        channel = item.data(0, Qt.ItemDataRole.UserRole)
        if channel and self.telemetry:
            # Add channel to the currently active plot tab
            current_widget = self.tab_widget.currentWidget()
            if isinstance(current_widget, PlotContainer):
                current_widget.add_channel_to_active_plot(channel, self.telemetry)
            elif isinstance(current_widget, PlotWidget):
                # Legacy support for old PlotWidget
                current_widget.add_channel(channel, self.telemetry)

    def _create_new_plot_tab(self):
        """Create a new plot tab."""
        # Create new plot container with sync callback and units manager
        plot_container = PlotContainer(
            sync_callback=self._synchronize_all_x_axes,
            units_manager=self.units_manager
        )

        # Set cursor synchronization for all plots in this container
        self._setup_cursor_sync_for_container(plot_container)

        self.plot_tabs.append(plot_container)

        # Add to tab widget with a default name
        tab_name = f"Plot {self.tab_counter}"
        tab_index = self.tab_widget.addTab(plot_container, tab_name)

        # Set as current tab
        self.tab_widget.setCurrentIndex(tab_index)

        # Enable renaming on double-click
        self.tab_widget.tabBarDoubleClicked.connect(self._rename_tab)

        self.tab_counter += 1

        # Synchronize X-axes across all plots
        self._synchronize_all_x_axes()

    def _close_tab(self, index: int):
        """Close a tab."""
        # Don't allow closing the last tab
        if self.tab_widget.count() <= 1:
            return

        widget = self.tab_widget.widget(index)
        if widget in self.plot_tabs:
            self.plot_tabs.remove(widget)

        self.tab_widget.removeTab(index)
        widget.deleteLater()

    def _rename_tab(self, index: int):
        """Rename a tab via double-click."""
        if index < 0:
            return

        current_name = self.tab_widget.tabText(index)

        # Create input dialog with dark theme
        dialog = QInputDialog(self)
        dialog.setWindowTitle("Rename Tab")
        dialog.setLabelText("Enter new tab name:")
        dialog.setTextValue(current_name)
        dialog.setStyleSheet("""
            QInputDialog {
                background-color: #1e1e1e;
            }
            QLabel {
                color: #dcdcdc;
            }
            QLineEdit {
                background-color: #3c3c3c;
                color: #dcdcdc;
                border: 1px solid #3e3e42;
                padding: 5px;
                selection-background-color: #094771;
            }
            QLineEdit:focus {
                border: 1px solid #007acc;
            }
            QPushButton {
                background-color: #0e639c;
                color: #ffffff;
                border: none;
                padding: 6px 16px;
                border-radius: 2px;
                min-width: 60px;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
            QPushButton:pressed {
                background-color: #007acc;
            }
        """)

        ok = dialog.exec()
        new_name = dialog.textValue()

        if ok and new_name:
            self.tab_widget.setTabText(index, new_name)

    def _show_tab_context_menu(self, position):
        """Show context menu when right-clicking a tab."""
        # Get the tab index at the clicked position
        tab_index = self.tab_widget.tabBar().tabAt(position)
        if tab_index < 0:
            return

        # Create context menu
        menu = QMenu(self)

        # Rename action
        rename_action = QAction("Rename Tab", self)
        rename_action.triggered.connect(lambda: self._rename_tab(tab_index))
        menu.addAction(rename_action)

        menu.addSeparator()

        # New tab action
        new_tab_action = QAction("New Tab", self)
        new_tab_action.triggered.connect(self._create_new_plot_tab)
        menu.addAction(new_tab_action)

        # Close tab action
        close_tab_action = QAction("Close Tab", self)
        close_tab_action.triggered.connect(lambda: self._close_tab(tab_index))
        # Disable if it's the last tab
        if self.tab_widget.count() <= 1:
            close_tab_action.setEnabled(False)
        menu.addAction(close_tab_action)

        # Show menu at cursor position
        menu.exec(self.tab_widget.tabBar().mapToGlobal(position))

    def _save_configuration(self):
        """Save current tab configuration to a file."""
        if not self.plot_tabs:
            QMessageBox.warning(
                self,
                "No Tabs",
                "There are no tabs to save."
            )
            return

        # Get default config directory
        default_dir = str(TabConfiguration.get_default_config_dir())

        # Open save dialog
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Tab Configuration",
            default_dir,
            "MFViewer Config (*.mfc);;JSON Files (*.json);;All Files (*.*)"
        )

        if not file_path:
            return

        # Collect tab data
        tabs_data = []
        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            if isinstance(widget, PlotContainer):
                tab_data = {
                    'name': self.tab_widget.tabText(i),
                    'container_config': widget.get_configuration()
                }
                tabs_data.append(tab_data)
            elif isinstance(widget, PlotWidget):
                # Legacy support
                tab_data = {
                    'name': self.tab_widget.tabText(i),
                    'channels': widget.get_channel_names()
                }
                tabs_data.append(tab_data)

        # Save configuration
        if TabConfiguration.save_configuration(file_path, tabs_data):
            self.statusbar.showMessage(f"Configuration saved to {Path(file_path).name}", 3000)
        else:
            QMessageBox.critical(
                self,
                "Save Failed",
                "Failed to save configuration file."
            )

    def _load_configuration(self):
        """Load tab configuration from a file."""
        if not self.telemetry:
            QMessageBox.warning(
                self,
                "No Data Loaded",
                "Please open a log file before loading a configuration."
            )
            return

        # Get default config directory
        default_dir = str(TabConfiguration.get_default_config_dir())

        # Open load dialog
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Tab Configuration",
            default_dir,
            "MFViewer Config (*.mfc);;JSON Files (*.json);;All Files (*.*)"
        )

        if not file_path:
            return

        # Load configuration
        tabs_data = TabConfiguration.load_configuration(file_path)
        if not tabs_data:
            QMessageBox.critical(
                self,
                "Load Failed",
                "Failed to load configuration file or invalid format."
            )
            return

        # Clear existing tabs
        while self.tab_widget.count() > 0:
            widget = self.tab_widget.widget(0)
            if widget in self.plot_tabs:
                self.plot_tabs.remove(widget)
            self.tab_widget.removeTab(0)
            widget.deleteLater()

        # Create tabs from configuration
        for tab_data in tabs_data:
            tab_name = tab_data.get('name', f'Plot {self.tab_counter}')

            # Check if this is a new PlotContainer config or legacy PlotWidget
            if 'container_config' in tab_data:
                # New format with PlotContainer
                plot_container = PlotContainer(
                    sync_callback=self._synchronize_all_x_axes,
                    units_manager=self.units_manager
                )
                self._setup_cursor_sync_for_container(plot_container)
                self.plot_tabs.append(plot_container)
                self.tab_widget.addTab(plot_container, tab_name)
                plot_container.load_configuration(tab_data['container_config'], self.telemetry)
            else:
                # Legacy format with single PlotWidget
                plot_widget = PlotWidget(units_manager=self.units_manager)
                self.plot_tabs.append(plot_widget)
                self.tab_widget.addTab(plot_widget, tab_name)

                # Add channels to the tab
                for channel_name in tab_data.get('channels', []):
                    channel = self.telemetry.get_channel(channel_name)
                    if channel:
                        plot_widget.add_channel(channel, self.telemetry)
                    else:
                        print(f"Warning: Channel '{channel_name}' not found in current log file")

            self.tab_counter += 1

        # Set first tab as active
        if self.tab_widget.count() > 0:
            self.tab_widget.setCurrentIndex(0)

        # Synchronize X-axes across all plots
        self._synchronize_all_x_axes()

        self.statusbar.showMessage(f"Configuration loaded from {Path(file_path).name}", 3000)

    def _update_window_title(self):
        """Update the window title with current file name."""
        if self.current_file:
            self.setWindowTitle(f"MFViewer - {self.current_file.name}")
        else:
            self.setWindowTitle("MFViewer - Motorsports Fusion Telemetry Viewer")

    def _restore_session(self):
        """Restore the last session if available."""
        session_file = str(TabConfiguration.get_session_file())
        session_data = TabConfiguration.load_session(session_file)

        if not session_data:
            return

        # Restore last log file
        last_log_file = session_data.get('last_log_file')
        if last_log_file and Path(last_log_file).exists():
            try:
                self.open_file(last_log_file)

                # Restore tabs after file is loaded
                tabs_data = session_data.get('tabs', [])
                if tabs_data and self.telemetry:
                    self._restore_tabs_from_data(tabs_data)

            except Exception as e:
                print(f"Failed to restore session: {e}")

    def _restore_tabs_from_data(self, tabs_data: list):
        """Restore tabs from configuration data."""
        # Clear existing tabs
        while self.tab_widget.count() > 0:
            widget = self.tab_widget.widget(0)
            if widget in self.plot_tabs:
                self.plot_tabs.remove(widget)
            self.tab_widget.removeTab(0)
            widget.deleteLater()

        # Create tabs from data
        for tab_data in tabs_data:
            tab_name = tab_data.get('name', f'Plot {self.tab_counter}')

            # Check if this is a new PlotContainer config or legacy PlotWidget
            if 'container_config' in tab_data:
                # New format with PlotContainer
                plot_container = PlotContainer(
                    sync_callback=self._synchronize_all_x_axes,
                    units_manager=self.units_manager
                )
                self._setup_cursor_sync_for_container(plot_container)
                self.plot_tabs.append(plot_container)
                self.tab_widget.addTab(plot_container, tab_name)
                plot_container.load_configuration(tab_data['container_config'], self.telemetry)
            else:
                # Legacy format - convert to PlotContainer with single plot
                plot_container = PlotContainer(
                    sync_callback=self._synchronize_all_x_axes,
                    units_manager=self.units_manager
                )
                self._setup_cursor_sync_for_container(plot_container)
                self.plot_tabs.append(plot_container)
                self.tab_widget.addTab(plot_container, tab_name)

                # Get the first (and only) plot widget in the container
                if plot_container.plot_widgets:
                    plot_widget = plot_container.plot_widgets[0]
                    # Add channels
                    for channel_name in tab_data.get('channels', []):
                        channel = self.telemetry.get_channel(channel_name)
                        if channel:
                            plot_widget.add_channel(channel, self.telemetry)

            self.tab_counter += 1

        # Set first tab as active
        if self.tab_widget.count() > 0:
            self.tab_widget.setCurrentIndex(0)

        # Synchronize X-axes across all plots
        self._synchronize_all_x_axes()

    def _save_session(self):
        """Save current session state."""
        if not self.plot_tabs:
            return

        # Collect tab data
        tabs_data = []
        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            if isinstance(widget, PlotContainer):
                tab_data = {
                    'name': self.tab_widget.tabText(i),
                    'container_config': widget.get_configuration()
                }
                tabs_data.append(tab_data)
            elif isinstance(widget, PlotWidget):
                # Legacy support
                tab_data = {
                    'name': self.tab_widget.tabText(i),
                    'channels': widget.get_channel_names()
                }
                tabs_data.append(tab_data)

        # Save session
        session_file = str(TabConfiguration.get_session_file())
        last_log_file = str(self.current_file) if self.current_file else None
        TabConfiguration.save_session(session_file, tabs_data, last_log_file)

    def closeEvent(self, event):
        """Handle window close event to save session."""
        self._save_session()
        event.accept()

    def _synchronize_all_x_axes(self):
        """Synchronize X-axis across all plots in all tabs."""
        # Collect all plot widgets from all tabs
        all_plot_widgets = []
        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            if isinstance(widget, PlotContainer):
                all_plot_widgets.extend(widget.get_all_plot_widgets())
            elif isinstance(widget, PlotWidget):
                all_plot_widgets.append(widget)

        if len(all_plot_widgets) < 2:
            return

        # Always use the first plot as the master (reset if needed)
        self.master_viewbox = all_plot_widgets[0].plot_widget.getViewBox()

        # Link all other plots to the master
        for plot_widget in all_plot_widgets[1:]:
            viewbox = plot_widget.plot_widget.getViewBox()
            try:
                viewbox.setXLink(self.master_viewbox)
            except RuntimeError:
                # ViewBox was deleted, skip it
                pass

    def _setup_cursor_sync_for_container(self, container: PlotContainer):
        """
        Set up cursor synchronization for a plot container.

        Args:
            container: PlotContainer to set up
        """
        # Store reference to MainWindow for global sync
        def create_global_sync_callback():
            def global_cursor_sync(x_pos: float):
                # Update ALL plots in ALL tabs
                for i in range(self.tab_widget.count()):
                    widget = self.tab_widget.widget(i)
                    if isinstance(widget, PlotContainer):
                        for plot in widget.plot_widgets:
                            # Temporarily disable cursor callback to avoid recursion
                            original_callback = plot.cursor_callback
                            plot.cursor_callback = None
                            # Ensure cursor is active on all plots
                            plot.cursor_active = True
                            plot.set_cursor_position(x_pos)
                            plot.cursor_callback = original_callback
            return global_cursor_sync

        # Replace the container's cursor moved handler
        container._global_cursor_sync = create_global_sync_callback()

        # Update the callback for existing plot widgets in this container
        for plot_widget in container.plot_widgets:
            plot_widget.cursor_callback = container._global_cursor_sync

        # Override the container's _on_cursor_moved to use global sync
        container._on_cursor_moved = lambda x_pos: container._global_cursor_sync(x_pos)

    def _show_about(self):
        """Show about dialog."""
        QMessageBox.about(
            self,
            "About MFViewer",
            "<h3>MFViewer 0.1.0</h3>"
            "<p>Motorsports Fusion Telemetry Viewer</p>"
            "<p>A Python-based desktop application for viewing and analyzing "
            "telemetry log files.</p>"
        )

    def _show_preferences(self):
        """Show preferences dialog."""
        dialog = PreferencesDialog(self.units_manager, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Apply new preferences
            preferences = dialog.get_preferences()

            # Update unit preferences
            if 'units' in preferences:
                self.units_manager.set_preferences(preferences['units'])

            # Update Haltech conversion setting
            if 'cancel_haltech_conversion' in preferences:
                self.units_manager.cancel_haltech_conversion = preferences['cancel_haltech_conversion']

            self._save_unit_preferences()

            # Refresh all plots to apply new units
            self._refresh_all_plots()

            self.statusbar.showMessage("Preferences updated", 3000)

    def _refresh_all_plots(self):
        """Refresh all plots with new unit preferences."""
        # Refresh all plot tabs with new unit conversions
        for i in range(self.tab_widget.count()):
            plot_tab = self.tab_widget.widget(i)

            # Handle both PlotContainer and legacy PlotWidget
            if isinstance(plot_tab, PlotContainer):
                plot_tab.refresh_with_new_units()
            elif isinstance(plot_tab, PlotWidget):
                plot_tab.refresh_with_new_units()

    def _load_unit_preferences(self):
        """Load unit preferences from file."""
        prefs_file = TabConfiguration.get_default_config_dir() / 'unit_preferences.json'
        if prefs_file.exists():
            try:
                import json
                with open(prefs_file, 'r') as f:
                    data = json.load(f)

                    # Support both old and new format
                    if isinstance(data, dict) and 'units' in data:
                        # New format
                        self.units_manager.set_preferences(data.get('units', {}))
                        self.units_manager.cancel_haltech_conversion = data.get('cancel_haltech_conversion', False)
                    else:
                        # Old format - just unit preferences
                        self.units_manager.set_preferences(data)
            except Exception as e:
                print(f"Error loading unit preferences: {e}")

    def _save_unit_preferences(self):
        """Save unit preferences to file."""
        prefs_file = TabConfiguration.get_default_config_dir() / 'unit_preferences.json'
        prefs_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            import json
            data = {
                'units': self.units_manager.get_preferences(),
                'cancel_haltech_conversion': self.units_manager.cancel_haltech_conversion
            }
            with open(prefs_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving unit preferences: {e}")
