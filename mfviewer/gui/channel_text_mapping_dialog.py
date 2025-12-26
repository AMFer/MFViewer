"""
Channel Text Mapping dialog for assigning text labels to channel values.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QGroupBox, QFormLayout,
    QDialogButtonBox, QListWidget, QListWidgetItem,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QFileDialog, QMessageBox, QSplitter, QWidget,
    QSpinBox, QLineEdit, QAbstractItemView
)
from PyQt6.QtCore import Qt

from mfviewer.utils.units import UnitsManager
from mfviewer.utils.config import TabConfiguration


class ChannelTextMappingDialog(QDialog):
    """Dialog for editing channel text mappings (value -> label)."""

    def __init__(self, units_manager: UnitsManager, channel_names: List[str], parent=None):
        super().__init__(parent)
        self.units_manager = units_manager
        self.channel_names = sorted(channel_names)
        self.current_config_file: Optional[Path] = None
        self.has_unsaved_changes = False

        # Working copy of state mappings
        self.working_mappings: Dict[str, Dict[int, str]] = {}
        self._load_from_units_manager()

        self.setWindowTitle("Channel Text Mapping")
        self.setMinimumWidth(800)
        self.setMinimumHeight(600)

        self._setup_ui()
        self._apply_dark_theme()
        self._populate_mapping_list()

    def _load_from_units_manager(self):
        """Load current state mappings from units manager."""
        # Deep copy the current state mappings
        for channel, mappings in self.units_manager.state_mappings.items():
            self.working_mappings[channel] = mappings.copy()

    def _setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout(self)

        # Top toolbar with Load/Save buttons
        toolbar_layout = QHBoxLayout()

        self.load_btn = QPushButton("Load...")
        self.load_btn.clicked.connect(self._load_configuration)
        toolbar_layout.addWidget(self.load_btn)

        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self._save_configuration)
        toolbar_layout.addWidget(self.save_btn)

        self.save_as_btn = QPushButton("Save As...")
        self.save_as_btn.clicked.connect(self._save_configuration_as)
        toolbar_layout.addWidget(self.save_as_btn)

        toolbar_layout.addSpacing(20)

        self.reset_defaults_btn = QPushButton("Reset to Defaults")
        self.reset_defaults_btn.clicked.connect(self._reset_to_defaults)
        toolbar_layout.addWidget(self.reset_defaults_btn)

        toolbar_layout.addStretch()

        self.config_label = QLabel("No configuration file loaded")
        self.config_label.setStyleSheet("color: #888888; font-style: italic;")
        toolbar_layout.addWidget(self.config_label)

        layout.addLayout(toolbar_layout)

        # Main splitter with mapping list and editor
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left side - Mapping list
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        list_label = QLabel("Channel Mappings:")
        list_label.setStyleSheet("font-weight: bold;")
        left_layout.addWidget(list_label)

        self.mapping_list = QListWidget()
        self.mapping_list.currentItemChanged.connect(self._on_mapping_selected)
        left_layout.addWidget(self.mapping_list)

        # Add/Delete buttons for mappings
        list_btn_layout = QHBoxLayout()
        self.add_mapping_btn = QPushButton("Add Mapping")
        self.add_mapping_btn.clicked.connect(self._add_mapping)
        list_btn_layout.addWidget(self.add_mapping_btn)

        self.delete_mapping_btn = QPushButton("Delete Mapping")
        self.delete_mapping_btn.clicked.connect(self._delete_mapping)
        self.delete_mapping_btn.setEnabled(False)
        list_btn_layout.addWidget(self.delete_mapping_btn)

        left_layout.addLayout(list_btn_layout)

        splitter.addWidget(left_widget)

        # Right side - Editor
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Channel selector
        channel_group = QGroupBox("Mapping Details")
        channel_layout = QFormLayout()

        self.channel_combo = QComboBox()
        self.channel_combo.addItems(self.channel_names)
        self.channel_combo.currentTextChanged.connect(self._on_channel_changed)
        self.channel_combo.setEnabled(False)
        channel_layout.addRow("Channel:", self.channel_combo)

        channel_group.setLayout(channel_layout)
        right_layout.addWidget(channel_group)

        # Value-Text table
        table_group = QGroupBox("Value to Text Mappings")
        table_layout = QVBoxLayout()

        self.value_table = QTableWidget()
        self.value_table.setColumnCount(2)
        self.value_table.setHorizontalHeaderLabels(["Value", "Text Label"])
        self.value_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.value_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.value_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.value_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.value_table.itemChanged.connect(self._on_table_item_changed)
        table_layout.addWidget(self.value_table)

        # Add/Remove row buttons
        row_btn_layout = QHBoxLayout()
        self.add_row_btn = QPushButton("Add Value")
        self.add_row_btn.clicked.connect(self._add_table_row)
        self.add_row_btn.setEnabled(False)
        row_btn_layout.addWidget(self.add_row_btn)

        self.remove_row_btn = QPushButton("Remove Value")
        self.remove_row_btn.clicked.connect(self._remove_table_row)
        self.remove_row_btn.setEnabled(False)
        row_btn_layout.addWidget(self.remove_row_btn)

        row_btn_layout.addStretch()
        table_layout.addLayout(row_btn_layout)

        table_group.setLayout(table_layout)
        right_layout.addWidget(table_group)

        splitter.addWidget(right_widget)

        # Set splitter proportions
        splitter.setSizes([250, 550])

        layout.addWidget(splitter)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel |
            QDialogButtonBox.StandardButton.Apply
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        button_box.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self._apply_changes)
        layout.addWidget(button_box)

    def _populate_mapping_list(self):
        """Populate the mapping list with current mappings."""
        self.mapping_list.clear()
        for channel_name in sorted(self.working_mappings.keys()):
            item = QListWidgetItem(channel_name)
            self.mapping_list.addItem(item)

        # Select first item if available
        if self.mapping_list.count() > 0:
            self.mapping_list.setCurrentRow(0)

    def _on_mapping_selected(self, current: QListWidgetItem, previous: QListWidgetItem):
        """Handle mapping selection change."""
        if current is None:
            self.delete_mapping_btn.setEnabled(False)
            self.channel_combo.setEnabled(False)
            self.add_row_btn.setEnabled(False)
            self.remove_row_btn.setEnabled(False)
            self.value_table.setRowCount(0)
            return

        self.delete_mapping_btn.setEnabled(True)
        self.channel_combo.setEnabled(True)
        self.add_row_btn.setEnabled(True)
        self.remove_row_btn.setEnabled(True)

        channel_name = current.text()

        # Update channel combo
        index = self.channel_combo.findText(channel_name)
        if index >= 0:
            self.channel_combo.blockSignals(True)
            self.channel_combo.setCurrentIndex(index)
            self.channel_combo.blockSignals(False)

        # Populate table with values
        self._populate_value_table(channel_name)

    def _populate_value_table(self, channel_name: str):
        """Populate the value table for a channel."""
        self.value_table.blockSignals(True)
        self.value_table.setRowCount(0)

        if channel_name in self.working_mappings:
            mappings = self.working_mappings[channel_name]
            for value, label in sorted(mappings.items()):
                row = self.value_table.rowCount()
                self.value_table.insertRow(row)

                value_item = QTableWidgetItem(str(value))
                value_item.setData(Qt.ItemDataRole.UserRole, value)  # Store original value
                self.value_table.setItem(row, 0, value_item)

                label_item = QTableWidgetItem(label)
                self.value_table.setItem(row, 1, label_item)

        self.value_table.blockSignals(False)

    def _on_channel_changed(self, channel_name: str):
        """Handle channel combo change."""
        current_item = self.mapping_list.currentItem()
        if current_item is None:
            return

        old_channel = current_item.text()
        if old_channel == channel_name:
            return

        # Check if new channel already has a mapping
        if channel_name in self.working_mappings:
            QMessageBox.warning(
                self,
                "Channel Already Mapped",
                f"The channel '{channel_name}' already has a text mapping defined."
            )
            # Revert combo
            index = self.channel_combo.findText(old_channel)
            if index >= 0:
                self.channel_combo.blockSignals(True)
                self.channel_combo.setCurrentIndex(index)
                self.channel_combo.blockSignals(False)
            return

        # Move mappings to new channel
        self.working_mappings[channel_name] = self.working_mappings.pop(old_channel)
        current_item.setText(channel_name)
        self.has_unsaved_changes = True

    def _on_table_item_changed(self, item: QTableWidgetItem):
        """Handle table cell edit."""
        current_item = self.mapping_list.currentItem()
        if current_item is None:
            return

        channel_name = current_item.text()
        row = item.row()

        # Get value and label from the row
        value_item = self.value_table.item(row, 0)
        label_item = self.value_table.item(row, 1)

        if value_item is None or label_item is None:
            return

        try:
            value = int(value_item.text())
            label = label_item.text()

            # Update working mappings
            if channel_name not in self.working_mappings:
                self.working_mappings[channel_name] = {}

            # Remove old value if it changed
            old_value = value_item.data(Qt.ItemDataRole.UserRole)
            if old_value is not None and old_value != value:
                if old_value in self.working_mappings[channel_name]:
                    del self.working_mappings[channel_name][old_value]

            # Set new mapping
            self.working_mappings[channel_name][value] = label
            value_item.setData(Qt.ItemDataRole.UserRole, value)
            self.has_unsaved_changes = True

        except ValueError:
            # Invalid value, ignore
            pass

    def _add_mapping(self):
        """Add a new channel mapping."""
        # Find first unmapped channel
        unmapped_channel = None
        for channel in self.channel_names:
            if channel not in self.working_mappings:
                unmapped_channel = channel
                break

        if unmapped_channel is None:
            QMessageBox.information(
                self,
                "All Channels Mapped",
                "All available channels already have text mappings defined."
            )
            return

        # Create empty mapping for the channel
        self.working_mappings[unmapped_channel] = {}

        # Add to list and select it
        item = QListWidgetItem(unmapped_channel)
        self.mapping_list.addItem(item)
        self.mapping_list.setCurrentItem(item)
        self.has_unsaved_changes = True

    def _delete_mapping(self):
        """Delete the selected channel mapping."""
        current_item = self.mapping_list.currentItem()
        if current_item is None:
            return

        channel_name = current_item.text()

        reply = QMessageBox.question(
            self,
            "Delete Mapping",
            f"Are you sure you want to delete the text mapping for '{channel_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            del self.working_mappings[channel_name]
            row = self.mapping_list.row(current_item)
            self.mapping_list.takeItem(row)
            self.has_unsaved_changes = True

    def _reset_to_defaults(self):
        """Reset all mappings to the built-in defaults."""
        reply = QMessageBox.question(
            self,
            "Reset to Defaults",
            "This will discard all custom mappings and restore the built-in defaults.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # Copy default mappings
            self.working_mappings.clear()
            for channel, mappings in self.units_manager.default_state_mappings.items():
                self.working_mappings[channel] = mappings.copy()

            self.current_config_file = None
            self.config_label.setText("Reset to defaults")
            self.config_label.setStyleSheet("color: #888888; font-style: italic;")
            self.has_unsaved_changes = True

            self._populate_mapping_list()

    def _add_table_row(self):
        """Add a new row to the value table."""
        current_item = self.mapping_list.currentItem()
        if current_item is None:
            return

        channel_name = current_item.text()

        # Find next available value
        existing_values = set(self.working_mappings.get(channel_name, {}).keys())
        next_value = 0
        while next_value in existing_values:
            next_value += 1

        row = self.value_table.rowCount()
        self.value_table.blockSignals(True)
        self.value_table.insertRow(row)

        value_item = QTableWidgetItem(str(next_value))
        value_item.setData(Qt.ItemDataRole.UserRole, next_value)
        self.value_table.setItem(row, 0, value_item)

        label_item = QTableWidgetItem("New Label")
        self.value_table.setItem(row, 1, label_item)

        self.value_table.blockSignals(False)

        # Update working mappings
        if channel_name not in self.working_mappings:
            self.working_mappings[channel_name] = {}
        self.working_mappings[channel_name][next_value] = "New Label"
        self.has_unsaved_changes = True

        # Select the new row for editing
        self.value_table.selectRow(row)
        self.value_table.editItem(label_item)

    def _remove_table_row(self):
        """Remove the selected row from the value table."""
        current_item = self.mapping_list.currentItem()
        if current_item is None:
            return

        selected_rows = self.value_table.selectionModel().selectedRows()
        if not selected_rows:
            return

        channel_name = current_item.text()
        row = selected_rows[0].row()

        value_item = self.value_table.item(row, 0)
        if value_item is not None:
            try:
                value = int(value_item.text())
                if channel_name in self.working_mappings:
                    if value in self.working_mappings[channel_name]:
                        del self.working_mappings[channel_name][value]
                        self.has_unsaved_changes = True
            except ValueError:
                pass

        self.value_table.removeRow(row)

    def _load_configuration(self):
        """Load text mappings from a file."""
        config_dir = TabConfiguration.get_default_config_dir()

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Text Mapping Configuration",
            str(config_dir),
            "JSON Files (*.json);;All Files (*.*)"
        )

        if not file_path:
            return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Validate format
            if not isinstance(data, dict) or 'mappings' not in data:
                raise ValueError("Invalid configuration file format")

            # Load mappings (convert string keys back to int)
            self.working_mappings.clear()
            for channel, mappings in data['mappings'].items():
                self.working_mappings[channel] = {
                    int(k): v for k, v in mappings.items()
                }

            self.current_config_file = Path(file_path)
            self.config_label.setText(f"Loaded: {self.current_config_file.name}")
            self.config_label.setStyleSheet("color: #4ec9b0;")
            self.has_unsaved_changes = False

            self._populate_mapping_list()

        except Exception as e:
            QMessageBox.critical(
                self,
                "Load Error",
                f"Failed to load configuration file:\n{e}"
            )

    def _save_configuration(self):
        """Save text mappings to the current file, or prompt for new file."""
        if self.current_config_file is None:
            self._save_configuration_as()
        else:
            self._do_save_configuration(self.current_config_file)

    def _save_configuration_as(self):
        """Save text mappings to a new file."""
        config_dir = TabConfiguration.get_default_config_dir()

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Text Mapping Configuration",
            str(config_dir / "text_mappings.json"),
            "JSON Files (*.json);;All Files (*.*)"
        )

        if not file_path:
            return

        # Ensure .json extension
        if not file_path.endswith('.json'):
            file_path += '.json'

        self._do_save_configuration(Path(file_path))

    def _do_save_configuration(self, file_path: Path):
        """Actually save the configuration to file."""
        try:
            data = {
                'version': '1.0',
                'mappings': self.working_mappings
            }

            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)

            self.current_config_file = file_path
            self.config_label.setText(f"Saved: {file_path.name}")
            self.config_label.setStyleSheet("color: #4ec9b0;")
            self.has_unsaved_changes = False

        except Exception as e:
            QMessageBox.critical(
                self,
                "Save Error",
                f"Failed to save configuration file:\n{e}"
            )

    def _apply_changes(self):
        """Apply changes to the units manager without closing."""
        # Update units manager state mappings
        self.units_manager.state_mappings.clear()
        for channel, mappings in self.working_mappings.items():
            self.units_manager.state_mappings[channel] = mappings.copy()

        self.has_unsaved_changes = False

    def _on_accept(self):
        """Handle OK button - apply and close."""
        self._apply_changes()
        self.accept()

    def get_mappings(self) -> Dict[str, Dict[int, str]]:
        """Get the working mappings."""
        return self.working_mappings.copy()

    def _apply_dark_theme(self):
        """Apply dark theme styling to the dialog."""
        from PyQt6.QtCore import Qt
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                color: #dcdcdc;
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
            QListWidget {
                background-color: #252526;
                color: #dcdcdc;
                border: 1px solid #3e3e42;
                border-radius: 3px;
                outline: none;
            }
            QListWidget::item {
                padding: 6px 8px;
            }
            QListWidget::item:selected {
                background-color: #094771;
                color: #ffffff;
            }
            QListWidget::item:hover {
                background-color: #2a2d2e;
            }
            QTableWidget {
                background-color: #252526;
                color: #dcdcdc;
                border: 1px solid #3e3e42;
                border-radius: 3px;
                gridline-color: #3e3e42;
                outline: none;
            }
            QTableWidget::item {
                padding: 4px 8px;
            }
            QTableWidget::item:selected {
                background-color: #094771;
                color: #ffffff;
            }
            QHeaderView::section {
                background-color: #333333;
                color: #dcdcdc;
                padding: 6px 8px;
                border: none;
                border-right: 1px solid #3e3e42;
                border-bottom: 1px solid #3e3e42;
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
                background-color: #4a4a4a;
            }
            QComboBox:focus {
                border: 1px solid #007acc;
            }
            QComboBox:disabled {
                background-color: #2d2d2d;
                color: #666666;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
                background-color: transparent;
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
                selection-color: #ffffff;
                border: 1px solid #3e3e42;
                outline: none;
            }
            QComboBox QAbstractItemView::item {
                padding: 5px;
                min-height: 20px;
            }
            QComboBox QAbstractItemView::item:hover {
                background-color: #2a2d2e;
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
            QPushButton:focus {
                outline: none;
                border: 1px solid #007acc;
            }
            QPushButton:disabled {
                background-color: #3c3c3c;
                color: #666666;
            }
            QDialogButtonBox {
                background-color: #1e1e1e;
            }
            QSplitter::handle {
                background-color: #3e3e42;
            }
            QSplitter::handle:horizontal {
                width: 2px;
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
        """)
