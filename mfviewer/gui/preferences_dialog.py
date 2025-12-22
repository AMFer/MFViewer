"""
Preferences dialog for user settings.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QGroupBox, QFormLayout,
    QDialogButtonBox, QScrollArea, QWidget, QCheckBox, QTextEdit
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

        self.setWindowTitle("Preferences")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)

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

        # Haltech conversion group
        haltech_group = self._create_haltech_conversion_group()
        scroll_layout.addWidget(haltech_group)

        # Units group
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

    def _create_haltech_conversion_group(self) -> QGroupBox:
        """Create the Haltech conversion preferences group."""
        group = QGroupBox("Haltech Data Conversion")
        layout = QVBoxLayout()

        # Explanation label
        info_label = QLabel(
            "The Haltech data files apply conversion formulas (e.g., y = x/10) to raw sensor values.\n"
            "Enable the option below to cancel these conversions and work with raw values."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #a0a0a0; font-size: 9pt;")
        layout.addWidget(info_label)

        # Checkbox to enable/disable cancellation
        self.cancel_conversion_cb = QCheckBox("Cancel Haltech conversions (show raw values)")
        self.cancel_conversion_cb.setChecked(self.units_manager.cancel_haltech_conversion)
        self.cancel_conversion_cb.setStyleSheet("""
            QCheckBox {
                color: #dcdcdc;
                spacing: 5px;
                padding: 5px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border: 1px solid #3e3e42;
                border-radius: 3px;
                background-color: #2d2d30;
            }
            QCheckBox::indicator:checked {
                background-color: #0e639c;
                border-color: #0e639c;
            }
        """)
        layout.addWidget(self.cancel_conversion_cb)

        group.setLayout(layout)
        return group

    def _create_units_group(self) -> QGroupBox:
        """Create the units preferences group."""
        group = QGroupBox("Unit Preferences")
        layout = QFormLayout()

        # Get all base units that have conversions
        base_units = self.units_manager.get_all_base_units()

        # Create combo box for each unit type
        unit_labels = {
            'K': 'Temperature',
            'kPa': 'Pressure (Gauge)',
            'kPa (Abs)': 'Pressure (Absolute)',
            'km/h': 'Speed',
            'L': 'Volume (Large)',
            'cc': 'Volume (Small)',
            'cc/min': 'Flow Rate',
            'λ': 'Air-Fuel Ratio',
        }

        for base_unit in base_units:
            label_text = unit_labels.get(base_unit, base_unit)
            label = QLabel(f"{label_text}:")

            combo = QComboBox()
            available_units = self.units_manager.get_available_units(base_unit)
            combo.addItems(available_units)

            self.unit_combos[base_unit] = combo
            layout.addRow(label, combo)

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
            Dictionary containing unit preferences and settings
        """
        preferences = {
            'units': {},
            'cancel_haltech_conversion': self.cancel_conversion_cb.isChecked()
        }
        for base_unit, combo in self.unit_combos.items():
            preferences['units'][base_unit] = combo.currentText()
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
