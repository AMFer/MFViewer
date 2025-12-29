"""
Main application window.
"""

import sys
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTabWidget, QFileDialog, QMessageBox,
    QStatusBar, QTreeWidget, QTreeWidgetItem,
    QLabel, QPushButton, QInputDialog, QMenu, QDialog, QProgressDialog
)
from PyQt6.QtCore import Qt, QSize, QCoreApplication, QThread, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence, QPalette, QColor, QCloseEvent, QPixmap

from mfviewer.data.parser import MFLogParser, TelemetryData, get_parser_backend
from mfviewer.data.log_manager import LogFileManager
from mfviewer.gui.plot_widget import PlotWidget
from mfviewer.gui.plot_container import PlotContainer
from mfviewer.gui.preferences_dialog import PreferencesDialog
from mfviewer.gui.channel_text_mapping_dialog import ChannelTextMappingDialog
from mfviewer.gui.debug_settings_dialog import DebugSettingsDialog
from mfviewer.utils.config import TabConfiguration
from mfviewer.utils.units import UnitsManager
from mfviewer.utils import debug_log
from mfviewer.widgets.log_list_widget import LogListWidget


class FileLoaderThread(QThread):
    """
    Background thread for non-blocking file loading.

    This keeps the UI responsive while parsing large CSV files.
    Uses the optimized parser with GPU/Polars acceleration when available.
    """
    # Signals
    progress = pyqtSignal(int, str)  # (percent, message)
    finished = pyqtSignal(object)    # TelemetryData
    error = pyqtSignal(str)          # Error message

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.file_path = file_path

    def run(self):
        """Parse the file in a background thread."""
        try:
            # Create parser with progress callback
            def progress_callback(percent: int, message: str):
                self.progress.emit(percent, message)

            parser = MFLogParser(
                self.file_path,
                use_cache=True,
                progress_callback=progress_callback
            )

            telemetry = parser.parse()
            self.finished.emit(telemetry)

        except Exception as e:
            self.error.emit(str(e))


def get_resource_path(relative_path: str) -> Path:
    """
    Get absolute path to resource, works for dev and PyInstaller.

    Args:
        relative_path: Path relative to the project root (e.g., 'Assets/MFSplash.png')

    Returns:
        Absolute path to the resource
    """
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        base_path = Path(sys._MEIPASS)
    else:
        # Running in development
        base_path = Path(__file__).parent.parent.parent
    return base_path / relative_path


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
        self.log_manager = LogFileManager()  # REPLACES self.telemetry
        self.current_file: Optional[Path] = None
        self.current_config_file: Optional[Path] = None  # Track current config file for Save
        self.last_directory: Optional[str] = None  # Last directory for file dialogs
        self.plot_tabs: list = []  # Track all plot tab widgets
        self.tab_counter: int = 1  # Counter for naming new tabs
        self.master_viewbox = None  # Master viewbox for X-axis synchronization
        self._global_cursor_x: Optional[float] = None  # Global cursor position for lazy tab sync

        # Initialize units manager
        self.units_manager = UnitsManager()
        self._load_unit_preferences()
        self._load_text_mappings()

        self.setWindowTitle("MFViewer - Motorsports Fusion Telemetry Viewer")
        self.setMinimumSize(1200, 800)

        self._apply_dark_theme()
        self._enable_dark_title_bar()
        self._setup_ui()
        self._setup_menus()
        self._setup_statusbar()
        self._restore_session()

    def _enable_dark_title_bar(self):
        """Enable dark title bar on Windows."""
        try:
            import ctypes
            hwnd = int(self.winId())
            # DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 20, ctypes.byref(ctypes.c_int(1)), ctypes.sizeof(ctypes.c_int)
            )
        except Exception:
            # Silently fail on non-Windows platforms or if DWM API is unavailable
            pass

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
            QStatusBar {
                background-color: #007acc;
                color: #ffffff;
            }
            QToolTip {
                background-color: #2d2d30;
                color: #dcdcdc;
                border: 1px solid #3e3e42;
                padding: 4px;
                border-radius: 2px;
            }
            QTreeWidget {
                background-color: #0d1117;
                color: #e6edf3;
                border: 1px solid #30363d;
                font-size: 9pt;
                outline: none;
            }
            QTreeWidget::item {
                padding: 4px 8px;
                border-radius: 3px;
                margin: 1px 2px;
            }
            QTreeWidget::item:selected {
                background-color: #1f6feb;
                color: #ffffff;
                border: 1px solid #388bfd;
            }
            QTreeWidget::item:hover:!selected {
                background-color: #161b22;
                border: 1px solid #30363d;
            }
            QTreeWidget::branch {
                background: transparent;
            }
            QTreeWidget::branch:has-siblings:!adjoins-item {
                border-image: none;
            }
            QTreeWidget::branch:has-siblings:adjoins-item {
                border-image: none;
            }
            QTreeWidget::branch:!has-children:!has-siblings:adjoins-item {
                border-image: none;
                background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5, stop:0 #58a6ff, stop:0.6 #58a6ff, stop:0.7 transparent);
                width: 8px;
                height: 8px;
                margin: 4px;
            }
            QTreeWidget::branch:has-children:!has-siblings:closed,
            QTreeWidget::branch:closed:has-children:has-siblings {
                border-image: none;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 transparent,
                    stop:0.3 #58a6ff,
                    stop:0.5 #79c0ff,
                    stop:0.7 #58a6ff,
                    stop:1 transparent);
                width: 14px;
                height: 3px;
                margin: 6px 2px;
            }
            QTreeWidget::branch:open:has-children:!has-siblings,
            QTreeWidget::branch:open:has-children:has-siblings {
                border-image: none;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 transparent,
                    stop:0.3 #58a6ff,
                    stop:0.5 #79c0ff,
                    stop:0.7 #58a6ff,
                    stop:1 transparent);
                width: 3px;
                height: 14px;
                margin: 2px 6px;
            }
            QHeaderView::section {
                background-color: #161b22;
                color: #58a6ff;
                padding: 6px 10px;
                border: none;
                border-bottom: 2px solid #1f6feb;
                font-weight: bold;
                font-size: 10pt;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
            QTreeWidget QScrollBar:vertical {
                background-color: #0d1117;
                width: 12px;
                border: none;
                margin: 0px;
            }
            QTreeWidget QScrollBar::handle:vertical {
                background-color: #30363d;
                border-radius: 6px;
                min-height: 30px;
                margin: 2px;
            }
            QTreeWidget QScrollBar::handle:vertical:hover {
                background-color: #484f58;
            }
            QTreeWidget QScrollBar::handle:vertical:pressed {
                background-color: #58a6ff;
            }
            QTreeWidget QScrollBar::add-line:vertical,
            QTreeWidget QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QTreeWidget QScrollBar::add-page:vertical,
            QTreeWidget QScrollBar::sub-page:vertical {
                background: none;
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

        # Left panel: Vertical splitter for log list and channel tree
        left_panel_splitter = QSplitter(Qt.Orientation.Vertical)

        # Log list widget (top)
        self.log_list_widget = LogListWidget()
        self.log_list_widget.setMinimumHeight(100)
        self.log_list_widget.log_activated.connect(self._on_log_activated)
        self.log_list_widget.log_removed.connect(self._on_log_removed)
        self.log_list_widget.log_context_menu.connect(self._on_log_context_menu)
        left_panel_splitter.addWidget(self.log_list_widget)

        # Channel tree (bottom)
        self.channel_tree = ChannelTreeWidget()
        self.channel_tree.setHeaderLabel("Channels")
        self.channel_tree.setMinimumWidth(200)
        self.channel_tree.setMaximumWidth(400)
        self.channel_tree.itemDoubleClicked.connect(self._on_channel_double_clicked)

        # Enable drag and drop
        self.channel_tree.setDragEnabled(True)
        self.channel_tree.setDragDropMode(ChannelTreeWidget.DragDropMode.DragOnly)

        left_panel_splitter.addWidget(self.channel_tree)

        # Set initial sizes for log list and channel tree (25% / 75%)
        left_panel_splitter.setSizes([100, 300])

        # Add left panel to main splitter
        self.splitter.addWidget(left_panel_splitter)

        # Set left panel to not stretch when window is resized
        self.splitter.setStretchFactor(0, 0)  # Left panel (index 0) won't stretch

        # Center panel: Tab widget for different views
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(False)  # Close via context menu only
        self.tab_widget.tabCloseRequested.connect(self._close_tab)

        # Enable context menu on tabs
        self.tab_widget.tabBar().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tab_widget.tabBar().customContextMenuRequested.connect(self._show_tab_context_menu)

        # Create corner widget with "+" button and logo
        corner_widget = QWidget()
        corner_layout = QHBoxLayout(corner_widget)
        corner_layout.setContentsMargins(0, 0, 0, 5)  # Add 5px bottom margin to move logo up
        corner_layout.setSpacing(8)
        corner_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Add "+" button for new tabs
        self.new_tab_button = QPushButton("+")
        self.new_tab_button.setMaximumSize(30, 30)
        self.new_tab_button.setToolTip("Create new plot tab")
        self.new_tab_button.clicked.connect(self._create_new_plot_tab)
        corner_layout.addWidget(self.new_tab_button, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Add config file label
        self.config_label = QLabel("")
        self.config_label.setStyleSheet("""
            QLabel {
                color: #888888;
                font-size: 9pt;
                font-style: italic;
                padding: 0 8px;
            }
        """)
        self.config_label.setToolTip("Currently loaded tab configuration")
        corner_layout.addWidget(self.config_label, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Add logo
        logo_path = get_resource_path('Assets/MFFlatTitle.png')
        if logo_path.exists():
            logo_label = QLabel()
            logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            logo_pixmap = QPixmap(str(logo_path))
            # Scale to fit tab bar height (35px)
            logo_pixmap = logo_pixmap.scaledToHeight(35, Qt.TransformationMode.SmoothTransformation)
            logo_label.setPixmap(logo_pixmap)
            logo_label.setScaledContents(False)
            corner_layout.addWidget(logo_label, alignment=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)

        self.tab_widget.setCornerWidget(corner_widget, Qt.Corner.TopRightCorner)

        # Enable renaming on double-click (connect once here, not in _create_new_plot_tab)
        self.tab_widget.tabBarDoubleClicked.connect(self._rename_tab)

        # Connect tab change to refresh stale tabs (performance optimization)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

        # Create first plot tab (don't auto-rename the initial tab)
        self._create_new_plot_tab(auto_rename=False)

        self.splitter.addWidget(self.tab_widget)

        # Set tab widget (plots) to stretch when window is resized
        self.splitter.setStretchFactor(1, 1)  # Tab widget (index 1) will stretch

        # Set initial splitter sizes (22% left, 78% right)
        self.splitter.setSizes([260, 940])

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

        refresh_action = QAction("&Refresh All Log Files", self)
        refresh_action.setShortcut(QKeySequence("F5"))
        refresh_action.triggered.connect(self._refresh_all_log_files)
        file_menu.addAction(refresh_action)

        file_menu.addSeparator()

        # Configuration save/load
        save_config_action = QAction("&Save Tab Configuration", self)
        save_config_action.setShortcut(QKeySequence.StandardKey.Save)
        save_config_action.triggered.connect(self._save_configuration)
        file_menu.addAction(save_config_action)

        save_as_config_action = QAction("Save Tab Configuration &As...", self)
        save_as_config_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        save_as_config_action.triggered.connect(self._save_configuration_as)
        file_menu.addAction(save_as_config_action)

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

        # Channel text mapping
        text_mapping_action = QAction("Channel &Text Mapping...", self)
        text_mapping_action.setShortcut(QKeySequence("Ctrl+T"))
        text_mapping_action.triggered.connect(self._show_channel_text_mapping)
        tools_menu.addAction(text_mapping_action)

        tools_menu.addSeparator()

        preferences_action = QAction("&Units...", self)
        preferences_action.setShortcut(QKeySequence("Ctrl+,"))
        preferences_action.triggered.connect(self._show_preferences)
        tools_menu.addAction(preferences_action)

        tools_menu.addSeparator()

        debug_settings_action = QAction("&Debug Settings...", self)
        debug_settings_action.triggered.connect(self._show_debug_settings)
        tools_menu.addAction(debug_settings_action)

        # Help menu
        help_menu = menubar.addMenu("&Help")

        about_action = QAction("&About MFViewer", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)


    def _setup_statusbar(self):
        """Set up the status bar."""
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        self.statusbar.showMessage("Ready")

    def open_file_dialog(self):
        """Open file dialog to select a log file."""
        # Use last directory if available, otherwise empty string
        start_dir = self.last_directory if self.last_directory else ""

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Telemetry Log File",
            start_dir,
            "CSV Files (*.csv);;All Files (*.*)"
        )

        if file_path:
            # Save the directory for next time
            self.last_directory = str(Path(file_path).parent)
            self.open_file(file_path)

    def open_file(self, file_path: str):
        """
        Open and parse a telemetry log file using background thread.

        Args:
            file_path: Path to the log file
        """
        # Store file path for use in callbacks
        self._loading_file_path = Path(file_path)
        self.current_file = self._loading_file_path

        # Create progress dialog with determinate progress bar
        self._progress_dialog = QProgressDialog(
            f"Loading {self._loading_file_path.name}...",
            None,  # No cancel button
            0, 100,
            self
        )
        self._progress_dialog.setWindowTitle(f"Loading Log File ({get_parser_backend()})")
        self._progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress_dialog.setMinimumDuration(0)
        self._progress_dialog.setMinimumWidth(450)
        self._progress_dialog.setValue(0)
        self._progress_dialog.setAutoClose(False)
        self._progress_dialog.setAutoReset(False)

        # Apply dark mode styling to progress dialog
        self._progress_dialog.setStyleSheet("""
            QProgressDialog {
                background-color: #1e1e1e;
            }
            QLabel {
                color: #dcdcdc;
                background-color: #1e1e1e;
                padding: 10px;
                font-size: 11pt;
            }
            QProgressBar {
                background-color: #3c3c3c;
                color: #dcdcdc;
                border: 1px solid #3e3e42;
                border-radius: 3px;
                text-align: center;
                min-height: 20px;
            }
            QProgressBar::chunk {
                background-color: #007acc;
                border-radius: 2px;
            }
        """)

        self._progress_dialog.show()
        self.statusbar.showMessage(f"Loading {self._loading_file_path.name} ({get_parser_backend()})...")

        # Create and start the loader thread
        self._loader_thread = FileLoaderThread(file_path, self)
        self._loader_thread.progress.connect(self._on_load_progress)
        self._loader_thread.finished.connect(self._on_load_finished)
        self._loader_thread.error.connect(self._on_load_error)
        self._loader_thread.start()

    def _on_load_progress(self, percent: int, message: str):
        """Handle progress updates from the loader thread."""
        try:
            if hasattr(self, '_progress_dialog') and self._progress_dialog is not None:
                self._progress_dialog.setValue(percent)
                self._progress_dialog.setLabelText(f"{message}")
        except (RuntimeError, AttributeError):
            # Dialog may have been deleted or is invalid
            pass

    def _on_load_finished(self, telemetry: TelemetryData):
        """Handle successful file load completion."""
        try:
            # Add to log manager
            log_file = self.log_manager.add_log_file(
                file_path=self._loading_file_path,
                telemetry=telemetry,
                is_active=True
            )

            # Update UI
            self.log_list_widget.add_log_file(log_file)
            self._populate_channel_tree()
            self._update_window_title()

            # Check if we have pending tabs to restore (from session restore)
            if hasattr(self, '_pending_tabs_data') and self._pending_tabs_data:
                self._restore_tabs_from_data(self._pending_tabs_data)
                self._pending_tabs_data = None
            else:
                # Refresh all existing plots
                self._refresh_all_plots()

            # Check if we have more log files to load (from session restore)
            if hasattr(self, '_pending_log_files') and self._pending_log_files:
                # Load the next log file after a short delay to allow UI to update
                next_log = self._pending_log_files.pop(0)
                QTimer.singleShot(100, lambda: self.open_file(next_log['path']))

            # Update status bar with backend info
            time_range = telemetry.get_time_range()
            duration = time_range[1] - time_range[0]
            self.statusbar.showMessage(
                f"Loaded: {log_file.display_name} - {len(telemetry.channels)} channels, "
                f"{len(telemetry.data)} samples, "
                f"{duration:.1f}s duration ({get_parser_backend()})"
            )

        except Exception as e:
            QMessageBox.critical(
                self,
                "Error Processing File",
                f"Failed to process loaded data:\n{str(e)}"
            )
            self.statusbar.showMessage("Failed to process file")
        finally:
            self._cleanup_loader()

    def _on_load_error(self, error_message: str):
        """Handle file load error."""
        QMessageBox.critical(
            self,
            "Error Loading File",
            f"Failed to load file:\n{error_message}"
        )
        self.statusbar.showMessage("Failed to load file")
        self._cleanup_loader()

    def _cleanup_loader(self):
        """Clean up loader thread and progress dialog."""
        if hasattr(self, '_progress_dialog') and self._progress_dialog:
            self._progress_dialog.close()
            self._progress_dialog = None

        if hasattr(self, '_loader_thread') and self._loader_thread:
            self._loader_thread.deleteLater()
            self._loader_thread = None

    def _populate_channel_tree(self):
        """Populate the channel tree with MAIN log's channels."""
        self.channel_tree.clear()

        main_log = self.log_manager.get_main_log()
        if not main_log:
            return

        telemetry = main_log.telemetry

        # Group channels by type
        type_groups = {}
        for channel in telemetry.channels:
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
        """Handle double-click on channel item - plot from ALL active logs."""
        channel = item.data(0, Qt.ItemDataRole.UserRole)
        if not channel:
            return

        # Get current plot widget
        current_widget = self.tab_widget.currentWidget()

        if isinstance(current_widget, PlotContainer):
            # Find focused plot or use last one
            focused_plot = None
            for plot in current_widget.plot_widgets:
                if plot.hasFocus() or plot.underMouse():
                    focused_plot = plot
                    break

            if not focused_plot and current_widget.plot_widgets:
                focused_plot = current_widget.plot_widgets[-1]

            if focused_plot:
                focused_plot.add_channel_from_all_logs(channel.name, self.log_manager)

        elif isinstance(current_widget, PlotWidget):
            # Legacy support
            current_widget.add_channel_from_all_logs(channel.name, self.log_manager)

    def _on_log_activated(self, index: int, is_active: bool):
        """Handle checkbox state change for a log file."""
        self.log_manager.set_active(index, is_active)

        # Update line style icons in log list
        self.log_list_widget.update_line_styles()

        # If main log changed, refresh channel tree
        self._populate_channel_tree()

        # Refresh all plots
        self._refresh_all_plots()

    def _on_log_removed(self, index: int):
        """Handle log file removal."""
        log_file = self.log_manager.get_log_at(index)
        if not log_file:
            return

        reply = QMessageBox.question(
            self, 'Remove Log File',
            f'Remove {log_file.display_name} from comparison?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.log_manager.remove_log_file(index)
            self.log_list_widget.remove_log_file(index)
            self._populate_channel_tree()
            self._refresh_all_plots()

    def _replace_log_file(self, index: int):
        """Replace a log file with a new one."""
        log_file = self.log_manager.get_log_at(index)
        if not log_file:
            return

        # Store current state
        was_active = log_file.is_active

        # Get starting directory
        start_dir = str(log_file.file_path.parent) if log_file.file_path.exists() else ""

        # Open file dialog
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Replace Log File",
            start_dir,
            "CSV Files (*.csv);;All Files (*.*)"
        )

        if not file_path:
            return  # User cancelled

        # Create progress dialog
        progress = QProgressDialog("Replacing log file...", None, 0, 0, self)
        progress.setWindowTitle("Replacing Log File")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setMinimumWidth(400)
        progress.setValue(0)

        # Apply dark mode styling to progress dialog
        progress.setStyleSheet("""
            QProgressDialog {
                background-color: #1e1e1e;
            }
            QLabel {
                color: #dcdcdc;
                background-color: #1e1e1e;
                padding: 10px;
                font-size: 11pt;
            }
            QProgressBar {
                background-color: #3c3c3c;
                color: #dcdcdc;
                border: 1px solid #3e3e42;
                border-radius: 3px;
                text-align: center;
                min-height: 20px;
            }
            QProgressBar::chunk {
                background-color: #007acc;
                border-radius: 2px;
            }
        """)

        progress.show()
        QCoreApplication.processEvents()

        try:
            # Parse new file
            progress.setLabelText(f"Parsing {Path(file_path).name}...")
            QCoreApplication.processEvents()
            from mfviewer.data.parser import MFLogParser
            parser = MFLogParser(file_path)
            new_telemetry = parser.parse()

            if new_telemetry is None:
                progress.close()
                QMessageBox.critical(
                    self,
                    "Parse Error",
                    f"Failed to parse the selected file."
                )
                return

            # Remove old log
            progress.setLabelText("Removing old log...")
            QCoreApplication.processEvents()
            self.log_manager.remove_log_file(index)
            self.log_list_widget.remove_log_file(index)

            # Add new log at the same position
            progress.setLabelText("Adding new log...")
            QCoreApplication.processEvents()
            new_log = self.log_manager.add_log_file(Path(file_path), new_telemetry, is_active=was_active)

            # Update UI
            progress.setLabelText("Updating UI...")
            QCoreApplication.processEvents()
            self.log_list_widget.add_log_file(new_log)
            self._populate_channel_tree()
            self._refresh_all_plots()

            progress.close()
            self.statusbar.showMessage(f"Replaced log with {Path(file_path).name}", 3000)

        except Exception as e:
            progress.close()
            QMessageBox.critical(
                self,
                "Replace Error",
                f"Failed to replace log file: {str(e)}"
            )

    def _refresh_all_log_files(self):
        """Reload all log files from disk and refresh plots."""
        if not self.log_manager.log_files:
            QMessageBox.information(
                self,
                "No Logs Loaded",
                "Please open at least one log file before refreshing."
            )
            return

        from mfviewer.data.parser import MFLogParser

        # Create progress dialog
        num_files = len(self.log_manager.log_files)
        progress = QProgressDialog("Refreshing log files...", None, 0, num_files + 1, self)
        progress.setWindowTitle("Refreshing Logs")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setMinimumWidth(400)
        progress.setValue(0)
        progress.setStyleSheet("""
            QProgressDialog {
                background-color: #1e1e1e;
            }
            QLabel {
                color: #dcdcdc;
                background-color: #1e1e1e;
                padding: 10px;
                font-size: 11pt;
            }
            QProgressBar {
                background-color: #3c3c3c;
                color: #dcdcdc;
                border: 1px solid #3e3e42;
                border-radius: 3px;
                text-align: center;
                min-height: 20px;
            }
            QProgressBar::chunk {
                background-color: #007acc;
                border-radius: 2px;
            }
        """)
        progress.show()
        QCoreApplication.processEvents()

        # Re-parse each file
        for i, log_file in enumerate(self.log_manager.log_files):
            progress.setLabelText(f"Refreshing {log_file.display_name}...")
            progress.setValue(i)
            QCoreApplication.processEvents()

            if log_file.file_path.exists():
                parser = MFLogParser(log_file.file_path)
                new_telemetry = parser.parse()
                if new_telemetry:
                    log_file.telemetry = new_telemetry

        # Refresh UI
        progress.setLabelText("Updating plots...")
        progress.setValue(num_files)
        QCoreApplication.processEvents()

        self._populate_channel_tree()
        self._refresh_all_plots()

        progress.close()
        self.statusbar.showMessage("All log files refreshed", 3000)

    def _on_log_context_menu(self, index: int, position):
        """Handle context menu request for a log file."""
        log_file = self.log_manager.get_log_at(index)
        if not log_file:
            return

        menu = QMenu(self)

        # Add Log action (same as File > Open)
        add_log_action = QAction("Add Log...", self)
        add_log_action.triggered.connect(self.open_file_dialog)
        menu.addAction(add_log_action)

        menu.addSeparator()

        # Activate/Deactivate action
        if log_file.is_active:
            deactivate_action = QAction("Deactivate Log", self)
            deactivate_action.triggered.connect(lambda: self._on_log_activated(index, False))
            menu.addAction(deactivate_action)
        else:
            activate_action = QAction("Activate Log", self)
            activate_action.triggered.connect(lambda: self._on_log_activated(index, True))
            menu.addAction(activate_action)

        menu.addSeparator()

        # Remove action
        remove_action = QAction("Remove Log", self)
        remove_action.triggered.connect(lambda: self._on_log_removed(index))
        menu.addAction(remove_action)

        # Replace action
        replace_action = QAction("Replace Log File...", self)
        replace_action.triggered.connect(lambda: self._replace_log_file(index))
        menu.addAction(replace_action)

        menu.exec(position)

    def _create_new_plot_tab(self, auto_rename: bool = True):
        """Create a new plot tab.

        Args:
            auto_rename: If True, automatically open rename dialog for the new tab
        """
        # Create new plot container with sync callback, units manager, and log manager
        plot_container = PlotContainer(
            sync_callback=self._synchronize_all_x_axes,
            units_manager=self.units_manager,
            log_manager=self.log_manager
        )

        # Set cursor synchronization for all plots in this container
        self._setup_cursor_sync_for_container(plot_container)

        self.plot_tabs.append(plot_container)

        # Add to tab widget with a default name
        tab_name = f"Plot {self.tab_counter}"
        tab_index = self.tab_widget.addTab(plot_container, tab_name)

        # Set as current tab
        self.tab_widget.setCurrentIndex(tab_index)

        self.tab_counter += 1

        # Synchronize X-axes across all plots
        self._synchronize_all_x_axes()

        # Automatically open rename dialog for new tab
        if auto_rename:
            self._rename_tab(tab_index)

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
        """Save current tab configuration (Save command - uses current file or prompts for new)."""
        if self.current_config_file:
            # Save to existing file
            self._do_save_configuration(str(self.current_config_file))
        else:
            # No current file, prompt for save as
            self._save_configuration_as()

    def _save_configuration_as(self):
        """Save current tab configuration to a new file (Save As command)."""
        if not self.plot_tabs:
            QMessageBox.warning(
                self,
                "No Tabs",
                "There are no tabs to save."
            )
            return

        # Get default config directory
        default_dir = str(TabConfiguration.get_default_config_dir())

        # Use current config file name as default if available
        default_name = ""
        if self.current_config_file:
            default_name = str(self.current_config_file)
        else:
            default_name = str(Path(default_dir) / "my_config.mfc")

        # Open save dialog
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Tab Configuration As",
            default_name,
            "MFViewer Config (*.mfc);;JSON Files (*.json);;All Files (*.*)"
        )

        if not file_path:
            return

        self._do_save_configuration(file_path)

    def _do_save_configuration(self, file_path: str):
        """Perform the actual save operation."""
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
            self.current_config_file = Path(file_path)
            self._update_config_label()
            self.statusbar.showMessage(f"Configuration saved to {Path(file_path).name}", 3000)
        else:
            QMessageBox.critical(
                self,
                "Save Failed",
                "Failed to save configuration file."
            )

    def _load_configuration(self):
        """Load tab configuration from a file."""
        # Check if we have a main log
        main_log = self.log_manager.get_main_log()
        if not main_log:
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

        # Create progress dialog
        progress = QProgressDialog("Loading tab configuration...", None, 0, len(tabs_data) + 1, self)
        progress.setWindowTitle("Loading Configuration")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        QCoreApplication.processEvents()

        # Clear existing tabs
        progress.setLabelText("Clearing existing tabs...")
        QCoreApplication.processEvents()

        while self.tab_widget.count() > 0:
            widget = self.tab_widget.widget(0)
            if widget in self.plot_tabs:
                self.plot_tabs.remove(widget)
            self.tab_widget.removeTab(0)
            widget.deleteLater()

        progress.setValue(1)
        QCoreApplication.processEvents()

        # Create tabs from configuration
        for idx, tab_data in enumerate(tabs_data):
            tab_name = tab_data.get('name', f'Plot {self.tab_counter}')
            progress.setLabelText(f"Loading tab '{tab_name}'...")
            progress.setValue(idx + 2)
            QCoreApplication.processEvents()

            # Check if this is a new PlotContainer config or legacy PlotWidget
            if 'container_config' in tab_data:
                # New format with PlotContainer
                plot_container = PlotContainer(
                    sync_callback=self._synchronize_all_x_axes,
                    units_manager=self.units_manager,
                    log_manager=self.log_manager
                )
                self.plot_tabs.append(plot_container)
                self.tab_widget.addTab(plot_container, tab_name)
                # Use main log's telemetry for loading configuration
                plot_container.load_configuration(tab_data['container_config'], main_log.telemetry)
                # Set up cursor sync AFTER loading config (so all plots exist)
                self._setup_cursor_sync_for_container(plot_container)
            else:
                # Legacy format with single PlotWidget
                plot_widget = PlotWidget(units_manager=self.units_manager)
                self.plot_tabs.append(plot_widget)
                self.tab_widget.addTab(plot_widget, tab_name)

                # Add channels to the tab from main log (defer auto-scale until all added)
                channels_to_add = tab_data.get('channels', [])
                for channel_name in channels_to_add:
                    channel = main_log.telemetry.get_channel(channel_name)
                    if channel:
                        plot_widget.add_channel(channel, main_log.telemetry, defer_auto_scale=True)
                    else:
                        print(f"Warning: Channel '{channel_name}' not found in current log file")
                # Single auto-scale after all channels added
                if channels_to_add:
                    plot_widget._auto_scale()

            self.tab_counter += 1

        # Set first tab as active
        if self.tab_widget.count() > 0:
            self.tab_widget.setCurrentIndex(0)

        # Synchronize X-axes across all plots
        self._synchronize_all_x_axes()

        # Track current config file for Save command
        self.current_config_file = Path(file_path)
        self._update_config_label()

        progress.setValue(len(tabs_data) + 1)
        progress.close()

        self.statusbar.showMessage(f"Configuration loaded from {Path(file_path).name}", 3000)

    def _update_window_title(self):
        """Update the window title with current file name."""
        if self.current_file:
            self.setWindowTitle(f"MFViewer - {self.current_file.name}")
        else:
            self.setWindowTitle("MFViewer - Motorsports Fusion Telemetry Viewer")

    def _update_config_label(self):
        """Update the config label with current configuration file name."""
        if self.current_config_file:
            self.config_label.setText(self.current_config_file.name)
            self.config_label.setToolTip(f"Configuration: {self.current_config_file}")
        else:
            self.config_label.setText("")
            self.config_label.setToolTip("No configuration loaded")

    def _restore_session(self):
        """Restore the last session if available."""
        session_file = str(TabConfiguration.get_session_file())
        session_data = TabConfiguration.load_session(session_file)

        if not session_data:
            return

        # Restore last directory
        last_directory = session_data.get('last_directory')
        if last_directory:
            self.last_directory = last_directory

        # Restore last config file path
        last_config_file = session_data.get('last_config_file')
        if last_config_file and Path(last_config_file).exists():
            self.current_config_file = Path(last_config_file)
            self._update_config_label()

        # Store pending tabs data to be restored after files load
        tabs_data = session_data.get('tabs', [])
        if tabs_data:
            self._pending_tabs_data = tabs_data

        # Check for multi-log session (version 1.1+)
        log_files_data = session_data.get('log_files', [])
        if log_files_data:
            # Restore multiple log files
            try:
                # Store log files info for sequential loading
                self._pending_log_files = [
                    lf for lf in log_files_data
                    if Path(lf['path']).exists()
                ]
                if self._pending_log_files:
                    # Load the first log file, rest will be loaded after
                    first_log = self._pending_log_files.pop(0)
                    self.open_file(first_log['path'])
            except Exception as e:
                print(f"Failed to restore session: {e}")
        else:
            # Fallback to single log file (version 1.0 compatibility)
            last_log_file = session_data.get('last_log_file')
            if last_log_file and Path(last_log_file).exists():
                try:
                    self.open_file(last_log_file)
                except Exception as e:
                    print(f"Failed to restore session: {e}")

    def _restore_tabs_from_data(self, tabs_data: list):
        """Restore tabs from configuration data."""
        # Get main log for restoring channels
        main_log = self.log_manager.get_main_log()
        if not main_log:
            return

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
                    units_manager=self.units_manager,
                    log_manager=self.log_manager
                )
                self.plot_tabs.append(plot_container)
                self.tab_widget.addTab(plot_container, tab_name)
                # Use main log's telemetry for loading configuration
                plot_container.load_configuration(tab_data['container_config'], main_log.telemetry)
                # Set up cursor sync AFTER loading config (so all plots exist)
                self._setup_cursor_sync_for_container(plot_container)
            else:
                # Legacy format - convert to PlotContainer with single plot
                plot_container = PlotContainer(
                    sync_callback=self._synchronize_all_x_axes,
                    units_manager=self.units_manager,
                    log_manager=self.log_manager
                )
                self.plot_tabs.append(plot_container)
                self.tab_widget.addTab(plot_container, tab_name)

                # Get the first (and only) plot widget in the container
                if plot_container.plot_widgets:
                    plot_widget = plot_container.plot_widgets[0]
                    # Add channels from main log (defer auto-scale until all added)
                    channels_to_add = tab_data.get('channels', [])
                    for channel_name in channels_to_add:
                        channel = main_log.telemetry.get_channel(channel_name)
                        if channel:
                            plot_widget.add_channel(channel, main_log.telemetry, defer_auto_scale=True)
                    # Single auto-scale after all channels added
                    if channels_to_add:
                        plot_widget._auto_scale()

                # Set up cursor sync AFTER adding channels
                self._setup_cursor_sync_for_container(plot_container)

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

        # Collect all log files from log_manager
        log_files_data = []
        for log_file in self.log_manager.log_files:
            log_files_data.append({
                'path': str(log_file.file_path),
                'active': log_file.is_active,
                'time_offset': log_file.time_offset
            })

        # Save session
        session_file = str(TabConfiguration.get_session_file())
        # Use first log file for backwards compatibility
        last_log_file = str(self.log_manager.log_files[0].file_path) if self.log_manager.log_files else None
        last_config_file = str(self.current_config_file) if self.current_config_file else None
        TabConfiguration.save_session(
            session_file, tabs_data, last_log_file, self.last_directory,
            last_config_file, log_files_data
        )

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

        if len(all_plot_widgets) < 1:
            return

        # Calculate global X-range from all plotted data
        global_x_min = None
        global_x_max = None

        for plot_widget in all_plot_widgets:
            for plot_info in plot_widget.plot_items.values():
                plot_item = plot_info['plot_item']
                x_data, _ = plot_item.getData()
                if x_data is not None and len(x_data) > 0:
                    x_min = x_data.min()
                    x_max = x_data.max()
                    if global_x_min is None or x_min < global_x_min:
                        global_x_min = x_min
                    if global_x_max is None or x_max > global_x_max:
                        global_x_max = x_max

        # If we have only one plot, just set its X-range
        if len(all_plot_widgets) == 1:
            if global_x_min is not None and global_x_max is not None:
                all_plot_widgets[0].plot_widget.setXRange(global_x_min, global_x_max, padding=0.02)
            self._setup_x_range_sync(all_plot_widgets)
            return

        # First, unlink any previously linked viewboxes
        # setXLink causes issues with horizontal layouts as it makes plots share view coordinates
        for plot_widget in all_plot_widgets:
            viewbox = plot_widget.plot_widget.getViewBox()
            try:
                viewbox.setXLink(None)
            except (RuntimeError, AttributeError):
                pass

        # Set the global X-range on ALL viewboxes
        if global_x_min is not None and global_x_max is not None:
            for plot_widget in all_plot_widgets:
                plot_widget.plot_widget.setXRange(global_x_min, global_x_max, padding=0.02)

        # Set up X-range change signal handling for manual sync
        # This replaces setXLink and works correctly for both horizontal and vertical layouts
        self._setup_x_range_sync(all_plot_widgets)

    def _setup_x_range_sync(self, all_plot_widgets):
        """Set up signal handlers for X-range synchronization across all plots."""
        if not all_plot_widgets:
            return

        # Create a sync function that updates all plots when one changes
        def create_x_range_sync(source_widget):
            def sync_x_range(viewbox, x_range):
                # Avoid recursion
                if getattr(self, '_syncing_x_range', False):
                    return
                self._syncing_x_range = True
                try:
                    for plot_widget in all_plot_widgets:
                        if plot_widget != source_widget:
                            # Check if the widget and its ViewBox still exist
                            try:
                                vb = plot_widget.plot_widget.getViewBox()
                                if vb is not None:
                                    plot_widget.plot_widget.setXRange(x_range[0], x_range[1], padding=0)
                            except (RuntimeError, AttributeError):
                                # Widget has been deleted, skip it
                                pass
                finally:
                    self._syncing_x_range = False
            return sync_x_range

        # Connect sigXRangeChanged signal for each plot
        for plot_widget in all_plot_widgets:
            viewbox = plot_widget.plot_widget.getViewBox()
            # Disconnect any previous connections to avoid duplicates
            try:
                viewbox.sigXRangeChanged.disconnect()
            except TypeError:
                pass  # No connections to disconnect
            # Connect new sync handler
            viewbox.sigXRangeChanged.connect(create_x_range_sync(plot_widget))

    def _setup_cursor_sync_for_container(self, container: PlotContainer):
        """
        Set up cursor synchronization for a plot container.

        Args:
            container: PlotContainer to set up
        """
        # Store reference to MainWindow for global sync
        def create_global_sync_callback():
            def global_cursor_sync(x_pos: float):
                # Store cursor position globally for lazy sync when switching tabs
                self._global_cursor_x = x_pos

                # Only update plots in the CURRENT visible tab for performance
                current_widget = self.tab_widget.currentWidget()
                if not isinstance(current_widget, PlotContainer):
                    return

                import time
                with debug_log.benchmark("Cursor sync (active tab only)") as m:
                    total_plots = len(current_widget.plot_widgets)
                    sync_start = time.perf_counter()

                    # Update internal cursor state on each plot (for legend updates)
                    # But DON'T repaint individual plot overlays
                    for plot in current_widget.plot_widgets:
                        # Temporarily disable cursor callback to avoid recursion
                        original_callback = plot.cursor_callback
                        plot.cursor_callback = None
                        plot.cursor_active = True
                        # Update cursor position but defer ALL repaints
                        plot.set_cursor_position(x_pos, defer_repaint=True)
                        plot.cursor_callback = original_callback
                        # Hide per-plot cursor overlay (container handles drawing)
                        if plot.cursor_line:
                            plot.cursor_line.setVisible(False)

                    # Use container's single cursor overlay for ONE repaint
                    # instead of N repaints (one per plot)
                    current_widget.set_cursor_position(x_pos)

                    m['extra']['plots'] = total_plots
                    m['extra']['total_sync_ms'] = f"{(time.perf_counter() - sync_start) * 1000:.3f}"
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
        # Create custom message box with logo
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("About MFViewer")

        # Load and scale splash screen image
        splash_path = get_resource_path('Assets/MFSplash.png')
        if splash_path.exists():
            pixmap = QPixmap(str(splash_path))
            # Scale to reasonable size for dialog (200px wide)
            pixmap = pixmap.scaledToWidth(200, Qt.TransformationMode.SmoothTransformation)
            msg_box.setIconPixmap(pixmap)

        msg_box.setText(
            "<h3>MFViewer 0.3.1</h3>"
            "<p>Motorsports Fusion Telemetry Viewer</p>"
        )
        msg_box.setInformativeText(
            "A Python-based desktop application for viewing and analyzing "
            "telemetry log files from Haltech ECUs."
        )
        msg_box.exec()

    def _show_preferences(self):
        """Show preferences dialog."""
        dialog = PreferencesDialog(self.units_manager, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Apply new preferences
            preferences = dialog.get_preferences()

            # Update unit preferences
            if 'units' in preferences:
                self.units_manager.set_preferences(preferences['units'])

            # Update multipliers (save for future use - not yet implemented in units manager)
            # TODO: Apply multipliers to type-based conversions
            if 'multipliers' in preferences:
                # Store multipliers for future implementation
                pass

            self._save_unit_preferences()

            # Refresh all plots to apply new units
            self._refresh_all_plots_with_new_units()

            self.statusbar.showMessage("Preferences updated", 3000)

    def _show_debug_settings(self):
        """Show debug settings dialog."""
        dialog = DebugSettingsDialog(self)
        dialog.exec()

    def _show_channel_text_mapping(self):
        """Show channel text mapping dialog."""
        # Get channel names from loaded logs
        channel_names = []
        main_log = self.log_manager.get_main_log()
        if main_log:
            channel_names = main_log.telemetry.get_channel_names()

        dialog = ChannelTextMappingDialog(self.units_manager, channel_names, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Save mappings to persistent file
            self._save_text_mappings()

            # Refresh all plots to show new text labels
            self._refresh_all_plots()

            self.statusbar.showMessage("Channel text mappings updated", 3000)

    def _refresh_all_plots(self):
        """
        Refresh plots with current active logs.

        Performance optimization: Only refreshes the currently visible tab immediately.
        Other tabs are marked as needing refresh and will be updated when switched to.
        """
        current_idx = self.tab_widget.currentIndex()

        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)

            if i == current_idx:
                # Refresh current tab immediately
                if isinstance(widget, PlotContainer):
                    for plot_widget in widget.plot_widgets:
                        plot_widget.refresh_with_multi_log(self.log_manager)
                    # Synchronize Y-axis widths after refresh
                    widget.synchronize_y_axis_widths()
                elif isinstance(widget, PlotWidget):
                    widget.refresh_with_multi_log(self.log_manager)
            else:
                # Mark hidden tabs as needing refresh
                if isinstance(widget, PlotContainer):
                    widget.needs_refresh = True
                elif isinstance(widget, PlotWidget):
                    widget.needs_refresh = True

    def _on_tab_changed(self, index: int):
        """
        Handle tab change - refresh stale tabs and sync cursor position.

        Args:
            index: Index of the newly selected tab
        """
        widget = self.tab_widget.widget(index)
        if widget is None:
            return

        # Check if tab needs refresh (was marked stale)
        if getattr(widget, 'needs_refresh', False):
            widget.needs_refresh = False
            if isinstance(widget, PlotContainer):
                for plot_widget in widget.plot_widgets:
                    plot_widget.refresh_with_multi_log(self.log_manager)
                # Synchronize Y-axis widths after refresh
                widget.synchronize_y_axis_widths()
            elif isinstance(widget, PlotWidget):
                widget.refresh_with_multi_log(self.log_manager)

        # Sync cursor position to the newly visible tab (lazy sync)
        if hasattr(self, '_global_cursor_x') and self._global_cursor_x is not None:
            if isinstance(widget, PlotContainer):
                for plot in widget.plot_widgets:
                    # Only update if cursor was active somewhere
                    original_callback = plot.cursor_callback
                    plot.cursor_callback = None
                    plot.cursor_active = True
                    plot.set_cursor_position(self._global_cursor_x)
                    plot.cursor_callback = original_callback

    def _refresh_all_plots_with_new_units(self):
        """
        Refresh plots with new unit preferences.

        Performance optimization: Only refreshes the currently visible tab immediately.
        Other tabs are marked as needing refresh and will be updated when switched to.
        """
        current_idx = self.tab_widget.currentIndex()

        for i in range(self.tab_widget.count()):
            plot_tab = self.tab_widget.widget(i)

            if i == current_idx:
                # Refresh current tab immediately
                if isinstance(plot_tab, PlotContainer):
                    plot_tab.refresh_with_new_units()
                elif isinstance(plot_tab, PlotWidget):
                    plot_tab.refresh_with_new_units()
            else:
                # Mark hidden tabs as needing refresh
                if isinstance(plot_tab, PlotContainer):
                    plot_tab.needs_refresh = True
                elif isinstance(plot_tab, PlotWidget):
                    plot_tab.needs_refresh = True

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

    def _load_text_mappings(self):
        """Load channel text mappings from file."""
        mappings_file = TabConfiguration.get_default_config_dir() / 'text_mappings.json'
        if mappings_file.exists():
            try:
                import json
                with open(mappings_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                if isinstance(data, dict) and 'mappings' in data:
                    # Convert string keys back to int
                    mappings = {}
                    for channel, channel_mappings in data['mappings'].items():
                        mappings[channel] = {int(k): v for k, v in channel_mappings.items()}
                    self.units_manager.set_state_mappings(mappings)
            except Exception as e:
                print(f"Error loading text mappings: {e}")

    def _save_text_mappings(self):
        """Save channel text mappings to file."""
        mappings_file = TabConfiguration.get_default_config_dir() / 'text_mappings.json'
        mappings_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            import json
            data = {
                'version': '1.0',
                'mappings': self.units_manager.get_state_mappings()
            }
            with open(mappings_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving text mappings: {e}")
