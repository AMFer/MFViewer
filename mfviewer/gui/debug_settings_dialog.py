"""
Debug settings dialog for configuring debug logging and viewing benchmarks.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGroupBox, QFormLayout,
    QDialogButtonBox, QCheckBox, QLineEdit,
    QFileDialog, QTextEdit, QTabWidget, QWidget,
    QSpinBox, QComboBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from pathlib import Path

from mfviewer.utils import debug_log


class DebugSettingsDialog(QDialog):
    """Dialog for configuring debug logging settings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Debug Settings")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)

        self._setup_ui()
        self._load_current_settings()
        self._apply_dark_theme()

    def _setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout(self)

        # Create tab widget
        tabs = QTabWidget()

        # Settings tab
        settings_tab = self._create_settings_tab()
        tabs.addTab(settings_tab, "Settings")

        # Benchmarks tab
        benchmarks_tab = self._create_benchmarks_tab()
        tabs.addTab(benchmarks_tab, "Benchmarks")

        layout.addWidget(tabs)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel |
            QDialogButtonBox.StandardButton.Apply
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        button_box.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(
            self._apply_settings
        )
        layout.addWidget(button_box)

    def _create_settings_tab(self) -> QWidget:
        """Create the settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Enable/disable group
        enable_group = QGroupBox("Debug Logging")
        enable_layout = QVBoxLayout()

        self.enable_checkbox = QCheckBox("Enable debug logging")
        self.enable_checkbox.stateChanged.connect(self._on_enable_changed)
        enable_layout.addWidget(self.enable_checkbox)

        # Status label
        self.status_label = QLabel()
        self.status_label.setStyleSheet("color: #888888; font-style: italic;")
        enable_layout.addWidget(self.status_label)

        enable_group.setLayout(enable_layout)
        layout.addWidget(enable_group)

        # Log file settings group
        file_group = QGroupBox("Log File Settings")
        file_layout = QFormLayout()

        # Log file path
        path_widget = QWidget()
        path_layout = QHBoxLayout(path_widget)
        path_layout.setContentsMargins(0, 0, 0, 0)

        self.log_path_edit = QLineEdit()
        self.log_path_edit.setReadOnly(True)
        path_layout.addWidget(self.log_path_edit)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_log_file)
        path_layout.addWidget(browse_btn)

        default_btn = QPushButton("Default")
        default_btn.clicked.connect(self._set_default_path)
        path_layout.addWidget(default_btn)

        file_layout.addRow("Log file:", path_widget)

        # Log level
        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        file_layout.addRow("Log level:", self.log_level_combo)

        # Max file size
        self.max_size_spin = QSpinBox()
        self.max_size_spin.setRange(1, 100)
        self.max_size_spin.setSuffix(" MB")
        self.max_size_spin.setValue(10)
        file_layout.addRow("Max file size:", self.max_size_spin)

        # Backup count
        self.backup_count_spin = QSpinBox()
        self.backup_count_spin.setRange(0, 10)
        self.backup_count_spin.setValue(3)
        file_layout.addRow("Backup files:", self.backup_count_spin)

        file_group.setLayout(file_layout)
        layout.addWidget(file_group)

        # Actions group
        actions_group = QGroupBox("Actions")
        actions_layout = QHBoxLayout()

        open_log_btn = QPushButton("Open Log File")
        open_log_btn.clicked.connect(self._open_log_file)
        actions_layout.addWidget(open_log_btn)

        open_folder_btn = QPushButton("Open Log Folder")
        open_folder_btn.clicked.connect(self._open_log_folder)
        actions_layout.addWidget(open_folder_btn)

        clear_log_btn = QPushButton("Clear Log File")
        clear_log_btn.clicked.connect(self._clear_log_file)
        actions_layout.addWidget(clear_log_btn)

        actions_layout.addStretch()

        actions_group.setLayout(actions_layout)
        layout.addWidget(actions_group)

        layout.addStretch()
        return widget

    def _create_benchmarks_tab(self) -> QWidget:
        """Create the benchmarks tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Info label
        info_label = QLabel(
            "Benchmark statistics are collected when debug logging is enabled.\n"
            "They show timing data for various operations to help identify performance bottlenecks."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #888888;")
        layout.addWidget(info_label)

        # Benchmark text area
        self.benchmark_text = QTextEdit()
        self.benchmark_text.setReadOnly(True)
        self.benchmark_text.setFont(QFont("Consolas", 9))
        layout.addWidget(self.benchmark_text)

        # Buttons
        btn_layout = QHBoxLayout()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_benchmarks)
        btn_layout.addWidget(refresh_btn)

        clear_btn = QPushButton("Clear Statistics")
        clear_btn.clicked.connect(self._clear_benchmarks)
        btn_layout.addWidget(clear_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        return widget

    def _load_current_settings(self):
        """Load current settings into the dialog."""
        settings = debug_log.load_settings()

        self.enable_checkbox.setChecked(settings.get('enabled', False))
        self.log_path_edit.setText(settings.get('log_file', str(debug_log.get_default_log_file())))

        level = settings.get('log_level', 'DEBUG')
        index = self.log_level_combo.findText(level)
        if index >= 0:
            self.log_level_combo.setCurrentIndex(index)

        self.max_size_spin.setValue(settings.get('max_file_size_mb', 10))
        self.backup_count_spin.setValue(settings.get('backup_count', 3))

        self._update_status()
        self._refresh_benchmarks()

    def _update_status(self):
        """Update the status label."""
        if debug_log.is_enabled():
            log_path = debug_log.get_log_file_path()
            self.status_label.setText(f"Logging active: {log_path}")
            self.status_label.setStyleSheet("color: #4ec9b0;")
        else:
            self.status_label.setText("Logging is disabled")
            self.status_label.setStyleSheet("color: #888888; font-style: italic;")

    def _on_enable_changed(self, state):
        """Handle enable checkbox state change."""
        pass  # Will be applied when OK/Apply is clicked

    def _browse_log_file(self):
        """Browse for log file location."""
        current_path = self.log_path_edit.text()
        if current_path:
            start_dir = str(Path(current_path).parent)
        else:
            start_dir = str(debug_log.get_default_log_dir())

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Select Log File",
            start_dir,
            "Log Files (*.log);;All Files (*.*)"
        )

        if file_path:
            self.log_path_edit.setText(file_path)

    def _set_default_path(self):
        """Set the log path to the default location."""
        self.log_path_edit.setText(str(debug_log.get_default_log_file()))

    def _open_log_file(self):
        """Open the log file in the default text editor."""
        import subprocess
        import sys

        log_path = Path(self.log_path_edit.text())
        if log_path.exists():
            if sys.platform == 'win32':
                subprocess.run(['notepad', str(log_path)])
            elif sys.platform == 'darwin':
                subprocess.run(['open', str(log_path)])
            else:
                subprocess.run(['xdg-open', str(log_path)])

    def _open_log_folder(self):
        """Open the log folder in the file explorer."""
        import subprocess
        import sys

        log_path = Path(self.log_path_edit.text())
        folder = log_path.parent
        folder.mkdir(parents=True, exist_ok=True)

        if sys.platform == 'win32':
            subprocess.run(['explorer', str(folder)])
        elif sys.platform == 'darwin':
            subprocess.run(['open', str(folder)])
        else:
            subprocess.run(['xdg-open', str(folder)])

    def _clear_log_file(self):
        """Clear the log file contents."""
        log_path = Path(self.log_path_edit.text())
        if log_path.exists():
            try:
                # Close current logging to release file handle
                was_enabled = debug_log.is_enabled()
                if was_enabled:
                    debug_log.shutdown()

                # Clear the file
                with open(log_path, 'w') as f:
                    f.write("")

                # Restart logging if it was enabled
                if was_enabled:
                    self._apply_settings()

            except Exception as e:
                print(f"Error clearing log file: {e}")

    def _refresh_benchmarks(self):
        """Refresh the benchmark display."""
        summary = debug_log.get_benchmark_summary()
        self.benchmark_text.setPlainText(summary)

    def _clear_benchmarks(self):
        """Clear benchmark statistics."""
        debug_log.clear_benchmark_stats()
        self._refresh_benchmarks()

    def _apply_settings(self):
        """Apply the current settings."""
        settings = {
            'enabled': self.enable_checkbox.isChecked(),
            'log_file': self.log_path_edit.text(),
            'log_level': self.log_level_combo.currentText(),
            'max_file_size_mb': self.max_size_spin.value(),
            'backup_count': self.backup_count_spin.value()
        }

        # Save settings
        debug_log.save_settings(settings)

        # Re-initialize logging with new settings
        if debug_log.is_enabled():
            debug_log.shutdown()

        debug_log.init_logging(
            enabled=settings['enabled'],
            log_file=settings['log_file'],
            log_level=settings['log_level'],
            max_file_size_mb=settings['max_file_size_mb'],
            backup_count=settings['backup_count']
        )

        self._update_status()

    def _on_accept(self):
        """Handle OK button click."""
        self._apply_settings()
        self.accept()

    def _apply_dark_theme(self):
        """Apply dark theme styling to the dialog."""
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                color: #dcdcdc;
            }
            QTabWidget::pane {
                border: 1px solid #3e3e42;
                background-color: #1e1e1e;
            }
            QTabBar::tab {
                background-color: #2d2d30;
                color: #dcdcdc;
                padding: 8px 16px;
                border: 1px solid #3e3e42;
                border-bottom: none;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #1e1e1e;
                border-bottom: 1px solid #1e1e1e;
            }
            QTabBar::tab:hover:!selected {
                background-color: #3e3e42;
            }
            QGroupBox {
                color: #dcdcdc;
                background-color: #252526;
                border: 1px solid #3e3e42;
                border-radius: 3px;
                margin-top: 12px;
                padding-top: 10px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #dcdcdc;
            }
            QLabel {
                color: #dcdcdc;
                background-color: transparent;
            }
            QCheckBox {
                color: #dcdcdc;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid #3e3e42;
                border-radius: 2px;
                background-color: #3c3c3c;
            }
            QCheckBox::indicator:checked {
                background-color: #007acc;
                border-color: #007acc;
            }
            QCheckBox::indicator:hover {
                border-color: #007acc;
            }
            QLineEdit {
                background-color: #3c3c3c;
                color: #dcdcdc;
                border: 1px solid #3e3e42;
                padding: 5px 8px;
                border-radius: 2px;
            }
            QLineEdit:focus {
                border: 1px solid #007acc;
            }
            QComboBox {
                background-color: #3c3c3c;
                color: #dcdcdc;
                border: 1px solid #3e3e42;
                padding: 5px 8px;
                border-radius: 2px;
                min-height: 20px;
            }
            QComboBox:hover {
                border: 1px solid #007acc;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #dcdcdc;
                margin-right: 5px;
            }
            QComboBox QAbstractItemView {
                background-color: #252526;
                color: #dcdcdc;
                selection-background-color: #094771;
                border: 1px solid #3e3e42;
            }
            QSpinBox {
                background-color: #3c3c3c;
                color: #dcdcdc;
                border: 1px solid #3e3e42;
                padding: 5px 8px;
                border-radius: 2px;
            }
            QSpinBox:focus {
                border: 1px solid #007acc;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                background-color: #3c3c3c;
                border: none;
                border-left: 1px solid #3e3e42;
                width: 16px;
            }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {
                background-color: #4a4a4a;
            }
            QSpinBox::up-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-bottom: 4px solid #dcdcdc;
            }
            QSpinBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 4px solid #dcdcdc;
            }
            QPushButton {
                background-color: #0e639c;
                color: #ffffff;
                border: none;
                padding: 6px 16px;
                border-radius: 2px;
                min-height: 22px;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
            QPushButton:pressed {
                background-color: #007acc;
            }
            QTextEdit {
                background-color: #1e1e1e;
                color: #dcdcdc;
                border: 1px solid #3e3e42;
                font-family: 'Consolas', 'Courier New', monospace;
            }
            QDialogButtonBox {
                background-color: #1e1e1e;
            }
        """)
