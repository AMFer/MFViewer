"""
Preferences dialog for user settings.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QGroupBox, QFormLayout,
    QDialogButtonBox, QScrollArea, QWidget, QCheckBox, QTextEdit, QDoubleSpinBox
)
from PyQt6.QtCore import Qt
from typing import Dict

from mfviewer.utils.units import UnitsManager


class PreferencesDialog(QDialog):
    """Dialog for editing user preferences."""

    def __init__(self, units_manager: UnitsManager, parent=None):
        super().__init__(parent)
        self.units_manager = units_manager
        self.unit_combos: Dict[str, QComboBox] = {}
        self.multiplier_spinboxes: Dict[str, QDoubleSpinBox] = {}

        self.setWindowTitle("Preferences")
        self.setMinimumWidth(700)
        self.setMinimumHeight(750)

        self._setup_ui()
        self._load_current_preferences()
        self._apply_dark_theme()

    def _setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout(self)

        # Create scroll area for preferences
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        # Units group (includes multipliers)
        units_group = self._create_units_group()
        scroll_layout.addWidget(units_group)

        # Conversion info group
        info_group = self._create_conversion_info_group()
        scroll_layout.addWidget(info_group)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel |
            QDialogButtonBox.StandardButton.RestoreDefaults
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        button_box.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(
            self._restore_defaults
        )
        layout.addWidget(button_box)

    def _create_units_group(self) -> QGroupBox:
        """Create the units preferences group."""
        group = QGroupBox("Unit Preferences and Data Multipliers")
        layout = QFormLayout()

        # Get all types from the type_to_unit_map (all channel types from log files)
        type_to_unit = self.units_manager.type_to_unit_map

        # Map of default multipliers/divisors for each type
        type_multipliers = {
            'Pressure': 10.0,
            'AbsPressure': 10.0,
            'Temperature': 10.0,
            'Angle': 10.0,
            'Current_mA_as_A': 1000.0,
            'BatteryVoltage': 1000.0,
            'AFR': 1000.0,
            'EngineSpeed': 1.0,
            'Speed': 1.0,
            'Percentage': 1.0,
            'Time_us': 1.0,
            'Time_ms': 1.0,
            'Raw': 1.0,
        }

        # Create row for each type with label, multiplier spinbox, and unit combo
        for channel_type in sorted(type_to_unit.keys()):
            base_unit = type_to_unit[channel_type]

            # Create label for channel type
            label = QLabel(f"{channel_type}:")

            # Create horizontal layout for spinbox and combo
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(10)

            # Create spinbox for multiplier/divisor
            spinbox = QDoubleSpinBox()
            spinbox.setRange(1.0, 10000.0)
            spinbox.setDecimals(1)
            spinbox.setSingleStep(1.0)
            spinbox.setValue(type_multipliers.get(channel_type, 1.0))
            spinbox.setPrefix("÷ ")
            spinbox.setMinimumWidth(100)
            spinbox.setMaximumWidth(120)
            self.multiplier_spinboxes[channel_type] = spinbox
            row_layout.addWidget(spinbox)

            # Create combo box with available units for this base unit
            combo = QComboBox()
            available_units = self.units_manager.get_available_units(base_unit)

            if available_units:
                combo.addItems(available_units)
                self.unit_combos[base_unit] = combo
            else:
                # No unit conversions available, just show the base unit
                combo.addItem(base_unit)
                combo.setEnabled(False)
                self.unit_combos[base_unit] = combo

            combo.setMinimumWidth(150)
            row_layout.addWidget(combo)
            row_layout.addStretch()

            layout.addRow(label, row_widget)

        group.setLayout(layout)
        return group

    def _create_conversion_info_group(self) -> QGroupBox:
        """Create a group showing conversion information."""
        group = QGroupBox("Channel Conversion Examples")
        layout = QVBoxLayout()

        # Text area to show conversion examples
        self.conversion_info_text = QTextEdit()
        self.conversion_info_text.setReadOnly(True)
        self.conversion_info_text.setMaximumHeight(150)
        self.conversion_info_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #dcdcdc;
                border: 1px solid #3e3e42;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 9pt;
                padding: 5px;
            }
        """)

        # Build conversion info text
        info_lines = []
        info_lines.append("Sample channel conversions from Haltech CSV:\n")
        info_lines.append("These formulas show how Haltech converts raw sensor values.")
        info_lines.append("When 'Cancel Haltech conversions' is enabled, the inverse is applied.\n")

        # Show a few example channels
        example_channels = [
            "Manifold Pressure",
            "Coolant Temperature",
            "Throttle Position",
            "RPM",
            "Wideband Sensor 1",
            "Battery Voltage"
        ]

        for channel_name in example_channels:
            if channel_name in self.units_manager.channel_conversions:
                formula = self.units_manager.channel_conversions[channel_name]
                unit = self.units_manager.get_base_unit(channel_name)

                # Show if inverse conversion is available
                has_inverse = channel_name in self.units_manager.channel_inverse_conversions
                inverse_marker = " ✓" if has_inverse else " ✗"

                info_lines.append(f"{inverse_marker} {channel_name} ({unit}): {formula}")

        self.conversion_info_text.setPlainText("\n".join(info_lines))
        layout.addWidget(self.conversion_info_text)

        group.setLayout(layout)
        return group

    def _load_current_preferences(self):
        """Load current preferences into the dialog."""
        preferences = self.units_manager.get_preferences()

        for base_unit, combo in self.unit_combos.items():
            preferred_unit = preferences.get(base_unit, base_unit)
            index = combo.findText(preferred_unit)
            if index >= 0:
                combo.setCurrentIndex(index)

    def _restore_defaults(self):
        """Restore default preferences."""
        defaults = self.units_manager.default_preferences

        for base_unit, combo in self.unit_combos.items():
            default_unit = defaults.get(base_unit, base_unit)
            index = combo.findText(default_unit)
            if index >= 0:
                combo.setCurrentIndex(index)

    def get_preferences(self) -> Dict:
        """
        Get the selected preferences.

        Returns:
            Dictionary containing unit preferences, multipliers, and settings
        """
        preferences = {
            'units': {},
            'multipliers': {}
        }
        for base_unit, combo in self.unit_combos.items():
            preferences['units'][base_unit] = combo.currentText()
        for channel_type, spinbox in self.multiplier_spinboxes.items():
            preferences['multipliers'][channel_type] = spinbox.value()
        return preferences

    def _apply_dark_theme(self):
        """Apply dark theme styling to the dialog."""
        # Set window flags to ensure proper styling
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
            QDoubleSpinBox {
                background-color: #3c3c3c;
                color: #dcdcdc;
                border: 1px solid #3e3e42;
                padding: 5px 8px;
                border-radius: 2px;
                min-height: 20px;
            }
            QDoubleSpinBox:hover {
                border: 1px solid #007acc;
                background-color: #4a4a4a;
            }
            QDoubleSpinBox:focus {
                border: 1px solid #007acc;
            }
            QDoubleSpinBox::up-button {
                background-color: #3c3c3c;
                border: none;
                border-left: 1px solid #3e3e42;
                width: 16px;
                subcontrol-origin: border;
                subcontrol-position: top right;
            }
            QDoubleSpinBox::up-button:hover {
                background-color: #4a4a4a;
            }
            QDoubleSpinBox::up-button:pressed {
                background-color: #007acc;
            }
            QDoubleSpinBox::up-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-bottom: 4px solid #dcdcdc;
                width: 0px;
                height: 0px;
            }
            QDoubleSpinBox::down-button {
                background-color: #3c3c3c;
                border: none;
                border-left: 1px solid #3e3e42;
                width: 16px;
                subcontrol-origin: border;
                subcontrol-position: bottom right;
            }
            QDoubleSpinBox::down-button:hover {
                background-color: #4a4a4a;
            }
            QDoubleSpinBox::down-button:pressed {
                background-color: #007acc;
            }
            QDoubleSpinBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 4px solid #dcdcdc;
                width: 0px;
                height: 0px;
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
            QDialogButtonBox {
                background-color: #1e1e1e;
            }
            QScrollArea {
                border: none;
                background-color: #1e1e1e;
            }
            QScrollArea > QWidget > QWidget {
                background-color: #1e1e1e;
            }
            QScrollBar:vertical {
                background-color: #1e1e1e;
                width: 14px;
                border: none;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background-color: #424242;
                border-radius: 7px;
                min-height: 30px;
                margin: 2px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #4e4e4e;
            }
            QScrollBar::handle:vertical:pressed {
                background-color: #007acc;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
        """)
