"""
Engine Configuration Dialog for setting up engine parameters for VE model fitting.

This dialog allows users to:
- Create and save engine profiles
- Configure engine parameters (displacement, torque peak, redline, etc.)
- Select cam profile and valve configuration
- Delete saved profiles
"""

from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QGroupBox, QFormLayout,
    QDialogButtonBox, QSpinBox, QDoubleSpinBox,
    QLineEdit, QMessageBox, QWidget
)
from PyQt6.QtCore import Qt

from mfviewer.data.engine_model import EngineConfig, EngineConfigManager


class EngineConfigDialog(QDialog):
    """Dialog for configuring engine parameters."""

    def __init__(self, current_config: Optional[EngineConfig] = None, parent=None):
        """Initialize the dialog.

        Args:
            current_config: Optional current configuration to edit
            parent: Parent widget
        """
        super().__init__(parent)
        self.current_config = current_config
        self.result_config: Optional[EngineConfig] = None

        self.setWindowTitle("Engine Configuration")
        self.setMinimumWidth(400)
        self.setModal(True)

        self._setup_ui()
        self._apply_dark_theme()
        self._load_saved_configs()

        # If we have a current config, load it
        if current_config:
            self._load_config(current_config)

    def _setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Profile selection
        profile_layout = QHBoxLayout()
        profile_layout.addWidget(QLabel("Profile:"))

        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(200)
        self.profile_combo.currentTextChanged.connect(self._on_profile_selected)
        profile_layout.addWidget(self.profile_combo, 1)

        self.delete_btn = QPushButton("Delete")
        self.delete_btn.clicked.connect(self._delete_profile)
        self.delete_btn.setMaximumWidth(60)
        profile_layout.addWidget(self.delete_btn)

        layout.addLayout(profile_layout)

        # Engine parameters group
        params_group = QGroupBox("Engine Parameters")
        params_layout = QFormLayout()
        params_layout.setSpacing(8)

        # Name
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Enter engine name...")
        params_layout.addRow("Name:", self.name_edit)

        # Displacement
        self.displacement_spin = QSpinBox()
        self.displacement_spin.setRange(100, 10000)
        self.displacement_spin.setValue(2000)
        self.displacement_spin.setSuffix(" cc")
        self.displacement_spin.setSingleStep(100)
        params_layout.addRow("Displacement:", self.displacement_spin)

        # Peak torque RPM
        self.torque_rpm_spin = QSpinBox()
        self.torque_rpm_spin.setRange(1000, 12000)
        self.torque_rpm_spin.setValue(4500)
        self.torque_rpm_spin.setSuffix(" RPM")
        self.torque_rpm_spin.setSingleStep(100)
        params_layout.addRow("Peak Torque RPM:", self.torque_rpm_spin)

        # Redline
        self.redline_spin = QSpinBox()
        self.redline_spin.setRange(2000, 15000)
        self.redline_spin.setValue(7000)
        self.redline_spin.setSuffix(" RPM")
        self.redline_spin.setSingleStep(100)
        params_layout.addRow("Redline:", self.redline_spin)

        # Valve configuration
        self.valve_combo = QComboBox()
        self.valve_combo.addItems(["2V", "4V"])
        self.valve_combo.setCurrentText("4V")
        self.valve_combo.currentTextChanged.connect(self._update_peak_ve_default)
        params_layout.addRow("Valves per Cylinder:", self.valve_combo)

        # Cam profile
        self.cam_combo = QComboBox()
        self.cam_combo.addItems(["stock", "mild", "aggressive"])
        self.cam_combo.setCurrentText("stock")
        params_layout.addRow("Cam Profile:", self.cam_combo)

        # Peak VE estimate
        self.peak_ve_spin = QDoubleSpinBox()
        self.peak_ve_spin.setRange(50.0, 150.0)
        self.peak_ve_spin.setValue(95.0)
        self.peak_ve_spin.setSuffix(" %")
        self.peak_ve_spin.setSingleStep(1.0)
        self.peak_ve_spin.setDecimals(1)
        params_layout.addRow("Peak VE Estimate:", self.peak_ve_spin)

        params_group.setLayout(params_layout)
        layout.addWidget(params_group)

        # Help text
        help_label = QLabel(
            "Tip: Set Peak Torque RPM to where you expect maximum torque.\n"
            "The model uses this to shape the VE curve across RPM."
        )
        help_label.setStyleSheet("color: #888888; font-style: italic;")
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        # Buttons
        button_layout = QHBoxLayout()

        self.save_btn = QPushButton("Save Profile")
        self.save_btn.clicked.connect(self._save_profile)
        button_layout.addWidget(self.save_btn)

        button_layout.addStretch()

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self._accept)
        self.button_box.rejected.connect(self.reject)
        button_layout.addWidget(self.button_box)

        layout.addLayout(button_layout)

    def _apply_dark_theme(self):
        """Apply dark theme styling."""
        self.setStyleSheet("""
            QDialog {
                background-color: #2d2d2d;
                color: #ffffff;
            }
            QLabel {
                color: #cccccc;
            }
            QGroupBox {
                color: #ffffff;
                font-weight: bold;
                border: 1px solid #555555;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px;
            }
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
                background-color: #3c3c3c;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 4px;
                min-height: 20px;
            }
            QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
                border-color: #0078d4;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #cccccc;
                margin-right: 5px;
            }
            QComboBox QAbstractItemView {
                background-color: #3c3c3c;
                color: #ffffff;
                selection-background-color: #0078d4;
            }
            QPushButton {
                background-color: #0e639c;
                color: #ffffff;
                border: none;
                border-radius: 3px;
                padding: 6px 16px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
            QPushButton:pressed {
                background-color: #0d5a8c;
            }
            QPushButton:disabled {
                background-color: #555555;
                color: #888888;
            }
            QDialogButtonBox QPushButton {
                min-width: 70px;
            }
        """)

    def _load_saved_configs(self):
        """Load saved configurations into the combo box."""
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()

        # Add "New Profile" option
        self.profile_combo.addItem("-- New Profile --")

        # Add saved profiles
        config_names = EngineConfigManager.get_config_names()
        for name in config_names:
            self.profile_combo.addItem(name)

        # Select current config if provided
        if self.current_config and self.current_config.name in config_names:
            self.profile_combo.setCurrentText(self.current_config.name)

        self.profile_combo.blockSignals(False)

    def _on_profile_selected(self, name: str):
        """Handle profile selection change."""
        if name == "-- New Profile --":
            # Clear form for new profile
            self.name_edit.clear()
            self.displacement_spin.setValue(2000)
            self.torque_rpm_spin.setValue(4500)
            self.redline_spin.setValue(7000)
            self.valve_combo.setCurrentText("4V")
            self.cam_combo.setCurrentText("stock")
            self.peak_ve_spin.setValue(95.0)
            self.delete_btn.setEnabled(False)
        else:
            # Load selected profile
            configs = EngineConfigManager.load_configs()
            if name in configs:
                self._load_config(configs[name])
            self.delete_btn.setEnabled(True)

    def _load_config(self, config: EngineConfig):
        """Load a configuration into the form."""
        self.name_edit.setText(config.name)
        self.displacement_spin.setValue(int(config.displacement_cc))
        self.torque_rpm_spin.setValue(int(config.peak_torque_rpm))
        self.redline_spin.setValue(int(config.redline_rpm))
        self.valve_combo.setCurrentText(config.valve_config)
        self.cam_combo.setCurrentText(config.cam_profile)
        self.peak_ve_spin.setValue(config.peak_ve_estimate)

    def _update_peak_ve_default(self, valve_config: str):
        """Update peak VE default based on valve configuration."""
        # Only update if current value is a default
        current = self.peak_ve_spin.value()
        if current in [88.0, 98.0, 95.0]:
            if valve_config == "2V":
                self.peak_ve_spin.setValue(88.0)
            else:
                self.peak_ve_spin.setValue(98.0)

    def _get_config_from_form(self) -> Optional[EngineConfig]:
        """Create EngineConfig from current form values."""
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(
                self, "Invalid Name",
                "Please enter a name for this engine configuration."
            )
            return None

        return EngineConfig(
            name=name,
            displacement_cc=float(self.displacement_spin.value()),
            peak_torque_rpm=float(self.torque_rpm_spin.value()),
            redline_rpm=float(self.redline_spin.value()),
            valve_config=self.valve_combo.currentText(),
            cam_profile=self.cam_combo.currentText(),
            peak_ve_estimate=self.peak_ve_spin.value()
        )

    def _save_profile(self):
        """Save the current profile."""
        config = self._get_config_from_form()
        if config is None:
            return

        # Check if overwriting existing profile
        existing_names = EngineConfigManager.get_config_names()
        if config.name in existing_names:
            reply = QMessageBox.question(
                self, "Overwrite Profile?",
                f"A profile named '{config.name}' already exists.\n"
                "Do you want to overwrite it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        EngineConfigManager.save_config(config)
        self._load_saved_configs()
        self.profile_combo.setCurrentText(config.name)

        QMessageBox.information(
            self, "Profile Saved",
            f"Engine profile '{config.name}' has been saved."
        )

    def _delete_profile(self):
        """Delete the selected profile."""
        name = self.profile_combo.currentText()
        if name == "-- New Profile --":
            return

        reply = QMessageBox.question(
            self, "Delete Profile?",
            f"Are you sure you want to delete '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if EngineConfigManager.delete_config(name):
            self._load_saved_configs()
            QMessageBox.information(
                self, "Profile Deleted",
                f"Engine profile '{name}' has been deleted."
            )
        else:
            QMessageBox.warning(
                self, "Delete Failed",
                f"Failed to delete profile '{name}'."
            )

    def _accept(self):
        """Accept the dialog with current settings."""
        self.result_config = self._get_config_from_form()
        if self.result_config is not None:
            self.accept()

    def get_config(self) -> Optional[EngineConfig]:
        """Get the resulting configuration.

        Returns:
            The configured EngineConfig, or None if cancelled
        """
        return self.result_config
