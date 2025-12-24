"""
Time synchronization dialog for multi-log comparison.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDoubleSpinBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QMessageBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


class TimeSyncDialog(QDialog):
    """Dialog for synchronizing time offsets across multiple log files."""

    def __init__(self, log_manager, parent=None):
        super().__init__(parent)
        self.log_manager = log_manager
        self.setWindowTitle("Time Synchronization")
        self.setModal(True)
        self.resize(700, 500)

        # Apply dark mode styling
        self._apply_dark_mode_style()

        # Track if changes were made
        self.changes_made = False

        self._setup_ui()
        self._populate_table()

    def _apply_dark_mode_style(self):
        """Apply dark mode styling to match the main window theme."""
        self.setStyleSheet("""
            QDialog {
                background-color: #2d2d30;
                color: #dcdcdc;
            }
            QLabel {
                color: #dcdcdc;
            }
            QTableWidget {
                background-color: #1e1e1e;
                alternate-background-color: #252526;
                color: #dcdcdc;
                gridline-color: #3e3e42;
                border: 1px solid #3e3e42;
                selection-background-color: #094771;
            }
            QTableWidget::item {
                padding: 5px;
            }
            QTableWidget::item:selected {
                background-color: #094771;
            }
            QHeaderView::section {
                background-color: #2d2d30;
                color: #dcdcdc;
                padding: 5px;
                border: 1px solid #3e3e42;
                font-weight: bold;
            }
            QGroupBox {
                color: #dcdcdc;
                border: 1px solid #3e3e42;
                border-radius: 4px;
                margin-top: 10px;
                padding-top: 10px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
                color: #dcdcdc;
            }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                padding: 6px 16px;
                border-radius: 2px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
            QPushButton:pressed {
                background-color: #094771;
            }
            QPushButton:default {
                background-color: #0e639c;
                border: 1px solid #007acc;
            }
            QDoubleSpinBox {
                background-color: #3c3c3c;
                color: #dcdcdc;
                border: 1px solid #3e3e42;
                border-radius: 2px;
                padding: 3px;
                selection-background-color: #094771;
            }
            QDoubleSpinBox:focus {
                border: 1px solid #007acc;
            }
            QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
                background-color: #3c3c3c;
                border: none;
                width: 16px;
            }
            QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {
                background-color: #4e4e52;
            }
            QDoubleSpinBox::up-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-bottom: 4px solid #dcdcdc;
                width: 0;
                height: 0;
            }
            QDoubleSpinBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 4px solid #dcdcdc;
                width: 0;
                height: 0;
            }
        """)

    def _setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout(self)

        # Header
        header_label = QLabel("Adjust Time Offsets for Log Comparison")
        header_font = QFont()
        header_font.setPointSize(12)
        header_font.setBold(True)
        header_label.setFont(header_font)
        layout.addWidget(header_label)

        # Description
        desc_label = QLabel(
            "Set time offsets to align logs for comparison. "
            "Positive values shift the log later (right), negative values shift earlier (left)."
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #aaa; margin-bottom: 10px;")
        layout.addWidget(desc_label)

        # Table for log files
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels([
            "Log File", "Original Start Time (s)", "Current Offset (s)", "New Offset (s)"
        ])

        # Configure table
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)

        layout.addWidget(self.table)

        # Quick actions group
        actions_group = QGroupBox("Quick Actions")
        actions_layout = QHBoxLayout(actions_group)

        # Auto-align to zero button
        auto_align_btn = QPushButton("Auto-Align All to Zero")
        auto_align_btn.setToolTip("Automatically align all logs to start at time 0")
        auto_align_btn.clicked.connect(self._auto_align_to_zero)
        actions_layout.addWidget(auto_align_btn)

        # Reset all button
        reset_btn = QPushButton("Reset All Offsets")
        reset_btn.setToolTip("Reset all time offsets to 0 (use original timestamps)")
        reset_btn.clicked.connect(self._reset_all_offsets)
        actions_layout.addWidget(reset_btn)

        # Align to main log button
        align_main_btn = QPushButton("Align to Main Log")
        align_main_btn.setToolTip("Align all logs to have the same start time as the main log")
        align_main_btn.clicked.connect(self._align_to_main_log)
        actions_layout.addWidget(align_main_btn)

        layout.addWidget(actions_group)

        # Dialog buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        apply_btn = QPushButton("Apply")
        apply_btn.setDefault(True)
        apply_btn.clicked.connect(self._apply_changes)
        button_layout.addWidget(apply_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

    def _populate_table(self):
        """Populate the table with current log files and their offsets."""
        logs = self.log_manager.log_files
        self.table.setRowCount(len(logs))

        for row, log in enumerate(logs):
            # Log file name
            name_item = QTableWidgetItem(log.display_name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if log.is_active:
                name_item.setForeground(Qt.GlobalColor.white)
            else:
                name_item.setForeground(Qt.GlobalColor.gray)
            self.table.setItem(row, 0, name_item)

            # Original start time
            time_range = log.telemetry.get_time_range()
            start_time = time_range[0] if time_range else 0.0
            start_item = QTableWidgetItem(f"{start_time:.3f}")
            start_item.setFlags(start_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            start_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 1, start_item)

            # Current offset
            current_item = QTableWidgetItem(f"{log.time_offset:.3f}")
            current_item.setFlags(current_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            current_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 2, current_item)

            # New offset (editable via spin box)
            offset_spin = QDoubleSpinBox()
            offset_spin.setRange(-10000.0, 10000.0)
            offset_spin.setDecimals(3)
            offset_spin.setSingleStep(0.1)
            offset_spin.setValue(log.time_offset)
            offset_spin.setSuffix(" s")
            offset_spin.setAlignment(Qt.AlignmentFlag.AlignRight)
            self.table.setCellWidget(row, 3, offset_spin)

    def _auto_align_to_zero(self):
        """Auto-align all logs to start at time 0."""
        for row in range(self.table.rowCount()):
            # Get the original start time
            start_text = self.table.item(row, 1).text()
            start_time = float(start_text)

            # Set the offset to negate the start time
            offset_spin = self.table.cellWidget(row, 3)
            offset_spin.setValue(-start_time)

    def _reset_all_offsets(self):
        """Reset all offsets to 0."""
        for row in range(self.table.rowCount()):
            offset_spin = self.table.cellWidget(row, 3)
            offset_spin.setValue(0.0)

    def _align_to_main_log(self):
        """Align all logs to have the same start time as the main (first active) log."""
        # Find the main log
        logs = self.log_manager.log_files
        main_log = None
        main_row = -1

        for row, log in enumerate(logs):
            if log.is_active:
                main_log = log
                main_row = row
                break

        if main_log is None:
            QMessageBox.warning(
                self,
                "No Main Log",
                "No active log found to align to."
            )
            return

        # Get main log's start time
        main_time_range = main_log.telemetry.get_time_range()
        if not main_time_range:
            return

        main_start = main_time_range[0]

        # Align all other logs to this start time
        for row, log in enumerate(logs):
            time_range = log.telemetry.get_time_range()
            if time_range:
                log_start = time_range[0]
                # Calculate offset to match main log's start time
                offset = main_start - log_start

                offset_spin = self.table.cellWidget(row, 3)
                offset_spin.setValue(offset)

    def _apply_changes(self):
        """Apply the time offset changes to the log manager."""
        logs = self.log_manager.log_files

        for row, log in enumerate(logs):
            offset_spin = self.table.cellWidget(row, 3)
            new_offset = offset_spin.value()

            # Update the log manager
            self.log_manager.set_time_offset(log.index, new_offset)

        self.changes_made = True
        self.accept()
