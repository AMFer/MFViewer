"""
VE Map Calculator Dialog for calculating fuel VE corrections from telemetry data.

This dialog allows users to:
- Load a base VE map from CSV
- Analyze telemetry log data to calculate VE corrections
- Visualize cell usage (hit count) and lambda errors
- Save corrected VE maps
"""

import json
import numpy as np
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QGroupBox, QFormLayout,
    QDialogButtonBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QFileDialog, QMessageBox,
    QWidget, QSpinBox, QRadioButton, QButtonGroup,
    QProgressDialog, QAbstractItemView, QStyledItemDelegate, QStyle
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QBrush, QPalette


class ColoredCellDelegate(QStyledItemDelegate):
    """Delegate that paints cell backgrounds from item data, overriding stylesheet."""

    def paint(self, painter, option, index):
        """Paint the cell with custom background color."""
        # Get background color from model data
        bg_color = index.data(Qt.ItemDataRole.BackgroundRole)

        if bg_color and isinstance(bg_color, (QColor, QBrush)):
            painter.save()
            if isinstance(bg_color, QBrush):
                painter.fillRect(option.rect, bg_color)
            else:
                painter.fillRect(option.rect, QBrush(bg_color))
            painter.restore()

        # Draw selection highlight if selected
        if option.state & QStyle.StateFlag.State_Selected:
            painter.save()
            painter.fillRect(option.rect, QColor(9, 71, 113, 150))  # Semi-transparent selection
            painter.restore()

        # Draw text
        text = index.data(Qt.ItemDataRole.DisplayRole)
        if text:
            fg_color = index.data(Qt.ItemDataRole.ForegroundRole)
            if fg_color and isinstance(fg_color, (QColor, QBrush)):
                if isinstance(fg_color, QBrush):
                    painter.setPen(fg_color.color())
                else:
                    painter.setPen(fg_color)
            else:
                painter.setPen(QColor(220, 220, 220))

            painter.drawText(option.rect, Qt.AlignmentFlag.AlignCenter, str(text))

from mfviewer.utils.units import UnitsManager
from mfviewer.utils.config import TabConfiguration
from mfviewer.data.ve_map_manager import VEMapManager, find_bin_index
from mfviewer.data.log_manager import LogFileManager


class VEMapDialog(QDialog):
    """Dialog for calculating VE map corrections from telemetry data."""

    def __init__(self, log_manager: LogFileManager, units_manager: UnitsManager, parent=None):
        super().__init__(parent)
        self.log_manager = log_manager
        self.units_manager = units_manager
        self.ve_map_manager = VEMapManager()

        # Map data
        self.base_ve_map: Optional[np.ndarray] = None
        self.corrected_ve_map: Optional[np.ndarray] = None
        self.hit_count_map: Optional[np.ndarray] = None
        self.error_map: Optional[np.ndarray] = None
        self.correction_map: Optional[np.ndarray] = None

        # Axis data
        self.rpm_axis: List[float] = []
        self.load_axis: List[float] = []
        self.load_type: str = "TPS"

        # Current view mode
        self.view_mode: str = "correction"  # "hit_count", "error", "correction"

        # Channel names discovered from logs
        self.available_channels: List[str] = []
        self._discover_channels()

        self.setWindowTitle("Fuel VE Map Calculator")
        self.setMinimumWidth(1400)
        self.setMinimumHeight(800)
        self.resize(1600, 900)

        self._setup_ui()
        self._apply_dark_theme()
        self._load_settings()

        # Load default map
        QTimer.singleShot(100, self._load_default_map)

    def _get_settings_file(self) -> Path:
        """Get the path to the VE map settings file."""
        return TabConfiguration.get_default_config_dir() / 've_map_settings.json'

    def _load_settings(self):
        """Load saved settings from config file."""
        settings_file = self._get_settings_file()
        if settings_file.exists():
            try:
                with open(settings_file, 'r') as f:
                    settings = json.load(f)
                self.min_samples_spin.setValue(settings.get('min_samples', 10))
            except (json.JSONDecodeError, IOError):
                pass  # Use defaults if file is corrupted

    def _save_settings(self):
        """Save current settings to config file."""
        settings_file = self._get_settings_file()
        settings_file.parent.mkdir(parents=True, exist_ok=True)
        settings = {
            'min_samples': self.min_samples_spin.value()
        }
        try:
            with open(settings_file, 'w') as f:
                json.dump(settings, f, indent=2)
        except IOError:
            pass  # Silently fail if we can't save

    def _discover_channels(self):
        """Discover available channels from loaded logs."""
        main_log = self.log_manager.get_main_log()
        if main_log and main_log.telemetry:
            self.available_channels = sorted(main_log.telemetry.get_channel_names())

    def _setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout(self)

        # Top toolbar
        toolbar_layout = QHBoxLayout()

        self.load_map_btn = QPushButton("Load Base Map...")
        self.load_map_btn.clicked.connect(self._load_map_dialog)
        toolbar_layout.addWidget(self.load_map_btn)

        self.save_map_btn = QPushButton("Save Corrected Map...")
        self.save_map_btn.clicked.connect(self._save_corrected_map)
        self.save_map_btn.setEnabled(False)
        toolbar_layout.addWidget(self.save_map_btn)

        toolbar_layout.addSpacing(20)

        self.calculate_btn = QPushButton("Calculate Corrections")
        self.calculate_btn.clicked.connect(self._calculate_corrections)
        self.calculate_btn.setEnabled(False)
        toolbar_layout.addWidget(self.calculate_btn)

        toolbar_layout.addStretch()

        self.status_label = QLabel("Load a base map to begin")
        self.status_label.setStyleSheet("color: #888888; font-style: italic;")
        toolbar_layout.addWidget(self.status_label)

        layout.addLayout(toolbar_layout)

        # Main content area - horizontal layout
        content_layout = QHBoxLayout()
        content_layout.setSpacing(10)

        # Left side - Map table (stretches to fill)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        map_label = QLabel("VE Map (Load % vs RPM):")
        map_label.setStyleSheet("font-weight: bold;")
        left_layout.addWidget(map_label)

        self.map_table = QTableWidget()
        self.map_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.map_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.map_table.cellClicked.connect(self._on_cell_clicked)
        self.map_table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        # Use custom delegate to paint background colors (overrides stylesheet)
        self.map_table.setItemDelegate(ColoredCellDelegate(self.map_table))
        left_layout.addWidget(self.map_table)

        # Cell info label
        self.cell_info_label = QLabel("")
        self.cell_info_label.setStyleSheet("color: #cccccc; padding: 4px;")
        left_layout.addWidget(self.cell_info_label)

        content_layout.addWidget(left_widget, 1)  # Stretch factor 1

        # Right side - Controls (compact, fixed narrow width)
        right_widget = QWidget()
        right_widget.setFixedWidth(200)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        # Channel Selection
        channel_group = QGroupBox("Channels")
        channel_layout = QVBoxLayout()
        channel_layout.setSpacing(2)

        self.load_channel_combo = QComboBox()
        self._populate_channel_combo(self.load_channel_combo, ["Fuel - Load (TPS)", "Fuel - Load (MAP)", "Throttle Position"])
        channel_layout.addWidget(QLabel("Load:"))
        channel_layout.addWidget(self.load_channel_combo)

        self.rpm_channel_combo = QComboBox()
        self._populate_channel_combo(self.rpm_channel_combo, ["Engine Speed", "RPM"])
        channel_layout.addWidget(QLabel("RPM:"))
        channel_layout.addWidget(self.rpm_channel_combo)

        self.target_lambda_combo = QComboBox()
        self._populate_channel_combo(self.target_lambda_combo, ["Target Lambda", "Target AFR", "Lambda Target"])
        channel_layout.addWidget(QLabel("Target:"))
        channel_layout.addWidget(self.target_lambda_combo)

        self.actual_lambda_combo = QComboBox()
        self._populate_channel_combo(self.actual_lambda_combo, ["Wideband O2 Overall", "Wideband O2 Bank 1", "Wideband O2 1", "Wideband Sensor 1", "Lambda 1"])
        channel_layout.addWidget(QLabel("Actual:"))
        channel_layout.addWidget(self.actual_lambda_combo)

        channel_group.setLayout(channel_layout)
        right_layout.addWidget(channel_group)

        # View Mode
        view_group = QGroupBox("View Mode")
        view_layout = QVBoxLayout()

        self.view_mode_group = QButtonGroup(self)

        self.view_correction_radio = QRadioButton("VE Correction (Base → New)")
        self.view_correction_radio.setChecked(True)
        self.view_mode_group.addButton(self.view_correction_radio, 0)
        view_layout.addWidget(self.view_correction_radio)

        self.view_hit_count_radio = QRadioButton("Hit Count Heatmap")
        self.view_mode_group.addButton(self.view_hit_count_radio, 1)
        view_layout.addWidget(self.view_hit_count_radio)

        self.view_error_radio = QRadioButton("Lambda Error Heatmap")
        self.view_mode_group.addButton(self.view_error_radio, 2)
        view_layout.addWidget(self.view_error_radio)

        self.view_mode_group.buttonClicked.connect(self._on_view_mode_changed)

        view_group.setLayout(view_layout)
        right_layout.addWidget(view_group)

        # Settings
        settings_group = QGroupBox("Settings")
        settings_layout = QHBoxLayout()
        settings_layout.addWidget(QLabel("Min Samples:"))
        self.min_samples_spin = QSpinBox()
        self.min_samples_spin.setRange(1, 1000)
        self.min_samples_spin.setValue(10)
        self.min_samples_spin.setToolTip("Minimum samples required to calculate a correction for a cell")
        self.min_samples_spin.valueChanged.connect(self._save_settings)
        settings_layout.addWidget(self.min_samples_spin)
        settings_group.setLayout(settings_layout)
        right_layout.addWidget(settings_group)

        # Statistics
        stats_group = QGroupBox("Statistics")
        stats_layout = QVBoxLayout()
        stats_layout.setSpacing(2)

        self.stats_total_label = QLabel("Samples: -")
        stats_layout.addWidget(self.stats_total_label)

        self.stats_cells_label = QLabel("Cells: -")
        stats_layout.addWidget(self.stats_cells_label)

        self.stats_max_error_label = QLabel("Max error: -")
        stats_layout.addWidget(self.stats_max_error_label)

        self.stats_avg_correction_label = QLabel("Avg corr: -")
        stats_layout.addWidget(self.stats_avg_correction_label)

        stats_group.setLayout(stats_layout)
        right_layout.addWidget(stats_group)

        # Color Legend
        legend_group = QGroupBox("Legend")
        legend_layout = QVBoxLayout()
        legend_layout.setSpacing(2)

        self.legend_labels: List[QLabel] = []
        for _ in range(5):
            label = QLabel("")
            label.setStyleSheet("padding: 1px 4px; border-radius: 2px; font-size: 11px;")
            legend_layout.addWidget(label)
            self.legend_labels.append(label)

        legend_group.setLayout(legend_layout)
        right_layout.addWidget(legend_group)

        # Add stretch at bottom to push controls up
        right_layout.addStretch()

        # Add right widget with no stretch (fixed width based on content)
        content_layout.addWidget(right_widget, 0)

        layout.addLayout(content_layout)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Close
        )
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # Update legend for initial view mode
        self._update_legend()

    def _populate_channel_combo(self, combo: QComboBox, preferred: List[str]):
        """Populate a channel combo box with available channels, prioritizing preferred ones."""
        combo.clear()

        # Add preferred channels that exist
        added = set()
        for channel in preferred:
            if channel in self.available_channels:
                combo.addItem(channel)
                added.add(channel)

        # Add separator if we found preferred channels
        if added:
            combo.insertSeparator(combo.count())

        # Add all other channels
        for channel in self.available_channels:
            if channel not in added:
                combo.addItem(channel)

    def _load_default_map(self):
        """Load the default base map."""
        default_path = self.ve_map_manager.get_default_map_path()
        if default_path.exists():
            self._load_map(default_path)

    def _load_map_dialog(self):
        """Show file dialog to load a base map."""
        config_dir = TabConfiguration.get_default_config_dir()
        default_path = self.ve_map_manager.get_default_map_path().parent

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Base VE Map",
            str(default_path),
            "CSV Files (*.csv);;All Files (*.*)"
        )

        if file_path:
            self._load_map(Path(file_path))

    def _load_map(self, file_path: Path):
        """Load a VE map from file."""
        try:
            self.base_ve_map, self.rpm_axis, self.load_axis, self.load_type = \
                VEMapManager.load_map(file_path)

            # Reset correction data
            self.corrected_ve_map = None
            self.hit_count_map = None
            self.error_map = None
            self.correction_map = None

            # Update UI
            self._setup_map_table()
            self._update_map_display()
            self._update_statistics()

            self.status_label.setText(f"Loaded: {file_path.name}")
            self.status_label.setStyleSheet("color: #4ec9b0;")

            # Enable calculate if we have logs
            self.calculate_btn.setEnabled(self.log_manager.get_main_log() is not None)
            self.save_map_btn.setEnabled(False)

        except Exception as e:
            QMessageBox.critical(
                self,
                "Load Error",
                f"Failed to load VE map:\n{e}"
            )

    def _setup_map_table(self):
        """Set up the map table structure."""
        if self.base_ve_map is None:
            return

        rows, cols = self.base_ve_map.shape

        self.map_table.setRowCount(rows)
        self.map_table.setColumnCount(cols)

        # Set column headers (RPM values)
        headers = [str(int(rpm)) for rpm in self.rpm_axis]
        self.map_table.setHorizontalHeaderLabels(headers)

        # Set row headers (Load values)
        row_headers = [f"{load:.0f}%" for load in self.load_axis]
        self.map_table.setVerticalHeaderLabels(row_headers)

        # Set columns to stretch to fill available space
        header = self.map_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        # Set rows to have consistent height
        vert_header = self.map_table.verticalHeader()
        vert_header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    def _update_map_display(self):
        """Update the map table display based on current view mode."""
        if self.base_ve_map is None:
            return

        rows, cols = self.base_ve_map.shape

        self.map_table.blockSignals(True)

        for row in range(rows):
            for col in range(cols):
                base_ve = self.base_ve_map[row, col]

                # Determine cell text and color based on view mode
                if self.view_mode == "correction":
                    text, color = self._get_correction_display(row, col, base_ve)
                elif self.view_mode == "hit_count":
                    text, color = self._get_hit_count_display(row, col, base_ve)
                else:  # error
                    text, color = self._get_error_display(row, col, base_ve)

                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                # Make item non-editable but allow selection
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)

                # Set background color using QBrush explicitly
                item.setBackground(QBrush(color))

                # Set text color based on background brightness
                brightness = (color.red() * 299 + color.green() * 587 + color.blue() * 114) / 1000
                text_color = QColor(255, 255, 255) if brightness < 128 else QColor(0, 0, 0)
                item.setForeground(QBrush(text_color))

                self.map_table.setItem(row, col, item)

        self.map_table.blockSignals(False)

        # Force viewport update to ensure colors are painted
        self.map_table.viewport().update()

    def _get_correction_display(self, row: int, col: int, base_ve: float) -> Tuple[str, QColor]:
        """Get display text and color for correction view."""
        if self.corrected_ve_map is not None:
            new_ve = self.corrected_ve_map[row, col]
            correction = self.correction_map[row, col] if self.correction_map is not None else 1.0

            if correction != 1.0:
                change_pct = (correction - 1.0) * 100
                text = f"{base_ve:.1f}→{new_ve:.1f}"
                color = self._get_correction_color(change_pct)
            else:
                text = f"{base_ve:.1f}"
                color = QColor(60, 60, 70)
        else:
            text = f"{base_ve:.1f}"
            color = QColor(60, 60, 70)

        return text, color

    def _get_hit_count_display(self, row: int, col: int, base_ve: float) -> Tuple[str, QColor]:
        """Get display text and color for hit count view."""
        if self.hit_count_map is not None:
            count = self.hit_count_map[row, col]
            max_count = np.max(self.hit_count_map) if np.max(self.hit_count_map) > 0 else 1
            text = str(count) if count > 0 else "-"
            color = self._get_hit_count_color(count, max_count)
        else:
            text = f"{base_ve:.1f}"
            color = QColor(60, 60, 70)

        return text, color

    def _get_error_display(self, row: int, col: int, base_ve: float) -> Tuple[str, QColor]:
        """Get display text and color for error view."""
        if self.error_map is not None:
            error = self.error_map[row, col]
            if not np.isnan(error):
                text = f"{error:+.1f}%"
                color = self._get_error_color(error)
            else:
                text = "-"
                color = QColor(40, 40, 50)
        else:
            text = f"{base_ve:.1f}"
            color = QColor(60, 60, 70)

        return text, color

    def _get_correction_color(self, change_pct: float) -> QColor:
        """Get color for correction percentage. Red = +VE (add fuel), Green = -VE (remove fuel)."""
        if abs(change_pct) < 1.0:
            return QColor(60, 60, 60)  # Minor change - neutral dark gray
        elif abs(change_pct) < 3.0:
            if change_pct > 0:
                return QColor(140, 70, 70)  # Small increase - dark red
            else:
                return QColor(70, 120, 70)  # Small decrease - dark green
        elif abs(change_pct) < 7.0:
            if change_pct > 0:
                return QColor(180, 80, 80)  # Medium increase - medium red
            else:
                return QColor(80, 160, 80)  # Medium decrease - medium green
        else:
            if change_pct > 0:
                return QColor(220, 90, 90)  # Large increase - bright red
            else:
                return QColor(90, 200, 90)  # Large decrease - bright green

    def _get_hit_count_color(self, count: int, max_count: int) -> QColor:
        """Get color for hit count."""
        if count == 0:
            return QColor(40, 40, 50)  # No data - dark

        ratio = count / max_count

        if ratio < 0.25:
            # Dark blue to cyan
            t = ratio / 0.25
            return QColor(int(40 + t * 20), int(60 + t * 140), int(120 + t * 80))
        elif ratio < 0.5:
            # Cyan to green
            t = (ratio - 0.25) / 0.25
            return QColor(int(60 - t * 20), int(200 + t * 30), int(200 - t * 100))
        elif ratio < 0.75:
            # Green to yellow
            t = (ratio - 0.5) / 0.25
            return QColor(int(40 + t * 180), int(230), int(100 - t * 50))
        else:
            # Yellow to orange
            t = (ratio - 0.75) / 0.25
            return QColor(int(220 + t * 35), int(230 - t * 80), int(50))

    def _get_error_color(self, error_pct: float) -> QColor:
        """Get color for lambda error percentage."""
        abs_error = abs(error_pct)

        if abs_error < 2.0:
            return QColor(60, 180, 80)  # Green - on target
        elif abs_error < 5.0:
            return QColor(200, 200, 60)  # Yellow - slight error
        elif abs_error < 10.0:
            return QColor(230, 150, 50)  # Orange - moderate error
        else:
            if error_pct > 0:
                return QColor(230, 70, 70)  # Red - lean
            else:
                return QColor(70, 100, 230)  # Blue - rich

    def _update_legend(self):
        """Update the color legend based on current view mode."""
        if self.view_mode == "correction":
            legends = [
                ("No change", QColor(60, 60, 60)),
                ("+1-3% (add fuel)", QColor(140, 70, 70)),
                ("+3-7% (add fuel)", QColor(220, 90, 90)),
                ("-1-3% (less fuel)", QColor(70, 120, 70)),
                ("-3-7% (less fuel)", QColor(90, 200, 90)),
            ]
        elif self.view_mode == "hit_count":
            legends = [
                ("No samples", QColor(40, 40, 50)),
                ("Few samples", QColor(60, 100, 160)),
                ("Medium samples", QColor(50, 200, 150)),
                ("Many samples", QColor(180, 230, 70)),
                ("Most samples", QColor(255, 180, 50)),
            ]
        else:  # error
            legends = [
                ("On target (<2%)", QColor(60, 180, 80)),
                ("Slight error (2-5%)", QColor(200, 200, 60)),
                ("Moderate error (5-10%)", QColor(230, 150, 50)),
                ("Large lean (>10%)", QColor(230, 70, 70)),
                ("Large rich (>10%)", QColor(70, 100, 230)),
            ]

        for i, (text, color) in enumerate(legends):
            label = self.legend_labels[i]
            label.setText(text)
            brightness = (color.red() * 299 + color.green() * 587 + color.blue() * 114) / 1000
            text_color = "#000000" if brightness > 128 else "#ffffff"
            label.setStyleSheet(
                f"background-color: rgb({color.red()}, {color.green()}, {color.blue()}); "
                f"color: {text_color}; padding: 4px 8px; border-radius: 2px;"
            )

    def _on_view_mode_changed(self, button):
        """Handle view mode radio button change."""
        button_id = self.view_mode_group.id(button)
        if button_id == 0:
            self.view_mode = "correction"
        elif button_id == 1:
            self.view_mode = "hit_count"
        else:
            self.view_mode = "error"

        self._update_map_display()
        self._update_legend()

    def _on_cell_clicked(self, row: int, col: int):
        """Handle cell click to show detailed info."""
        if self.base_ve_map is None:
            return

        rpm = self.rpm_axis[col]
        load = self.load_axis[row]
        base_ve = self.base_ve_map[row, col]

        info_parts = [f"RPM: {rpm:.0f}", f"Load: {load:.0f}%", f"Base VE: {base_ve:.1f}%"]

        if self.hit_count_map is not None:
            info_parts.append(f"Samples: {self.hit_count_map[row, col]}")

        if self.error_map is not None and not np.isnan(self.error_map[row, col]):
            info_parts.append(f"Error: {self.error_map[row, col]:+.1f}%")

        if self.corrected_ve_map is not None:
            new_ve = self.corrected_ve_map[row, col]
            if new_ve != base_ve:
                info_parts.append(f"New VE: {new_ve:.1f}%")

        self.cell_info_label.setText("  |  ".join(info_parts))

    def _on_cell_double_clicked(self, row: int, col: int):
        """Handle cell double-click to remove correction for that cell."""
        if self.base_ve_map is None or self.correction_map is None:
            return

        # Reset this cell's correction
        self.correction_map[row, col] = 1.0
        self.corrected_ve_map[row, col] = self.base_ve_map[row, col]
        if self.error_map is not None:
            self.error_map[row, col] = np.nan

        # Update display
        self._update_map_display()
        self._update_statistics()

        # Update cell info to reflect the change
        self._on_cell_clicked(row, col)

    def _calculate_corrections(self):
        """Calculate VE corrections from telemetry data."""
        if self.base_ve_map is None:
            QMessageBox.warning(self, "No Map", "Please load a base map first.")
            return

        main_log = self.log_manager.get_main_log()
        if main_log is None:
            QMessageBox.warning(self, "No Log", "Please load a telemetry log file first.")
            return

        # Get channel names
        load_channel = self.load_channel_combo.currentText()
        rpm_channel = self.rpm_channel_combo.currentText()
        target_lambda_channel = self.target_lambda_combo.currentText()
        actual_lambda_channel = self.actual_lambda_combo.currentText()

        # Validate channels exist
        telemetry = main_log.telemetry
        missing = []
        for ch_name, ch_label in [(load_channel, "Load"), (rpm_channel, "RPM"),
                                   (target_lambda_channel, "Target Lambda"),
                                   (actual_lambda_channel, "Actual Lambda")]:
            if telemetry.get_channel(ch_name) is None:
                missing.append(f"{ch_label}: {ch_name}")

        if missing:
            QMessageBox.warning(
                self,
                "Missing Channels",
                f"The following channels were not found in the log:\n\n" +
                "\n".join(missing)
            )
            return

        # Show progress dialog
        progress = QProgressDialog("Calculating corrections...", "Cancel", 0, 100, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        try:
            # Collect binned data from all active logs
            binned_data = self._collect_binned_data(
                load_channel, rpm_channel, target_lambda_channel, actual_lambda_channel,
                progress
            )

            if progress.wasCanceled():
                return

            progress.setValue(70)
            progress.setLabelText("Computing corrections...")

            # Calculate corrections
            self._compute_corrections(binned_data, self.min_samples_spin.value())

            progress.setValue(90)
            progress.setLabelText("Updating display...")

            # Update display
            self._update_map_display()
            self._update_statistics()

            progress.setValue(100)

            self.status_label.setText("Corrections calculated")
            self.status_label.setStyleSheet("color: #4ec9b0;")
            self.save_map_btn.setEnabled(True)

        except Exception as e:
            progress.close()
            QMessageBox.critical(
                self,
                "Calculation Error",
                f"Failed to calculate corrections:\n{e}"
            )

    def _collect_binned_data(self, load_channel: str, rpm_channel: str,
                             target_lambda_channel: str, actual_lambda_channel: str,
                             progress: QProgressDialog) -> Dict[Tuple[int, int], List[float]]:
        """Collect lambda correction ratios binned by RPM and Load."""
        binned_data = defaultdict(list)

        active_logs = self.log_manager.get_active_logs()
        total_logs = len(active_logs)

        for log_idx, log_file in enumerate(active_logs):
            if progress.wasCanceled():
                break

            progress.setValue(int(10 + (log_idx / total_logs) * 50))
            progress.setLabelText(f"Processing log {log_idx + 1}/{total_logs}...")

            telemetry = log_file.telemetry

            # Get channel data
            load_series = telemetry.get_channel_data(load_channel)
            rpm_series = telemetry.get_channel_data(rpm_channel)
            target_series = telemetry.get_channel_data(target_lambda_channel)
            actual_series = telemetry.get_channel_data(actual_lambda_channel)

            if any(s is None for s in [load_series, rpm_series, target_series, actual_series]):
                continue

            # Convert to numpy arrays
            load_values = load_series.to_numpy().astype(np.float64)
            rpm_values = rpm_series.to_numpy().astype(np.float64)
            target_values = target_series.to_numpy().astype(np.float64)
            actual_values = actual_series.to_numpy().astype(np.float64)

            # Apply unit conversions based on channel type
            load_channel_info = telemetry.get_channel(load_channel)
            if load_channel_info:
                load_values = self.units_manager.apply_channel_conversion(
                    load_channel, load_values, load_channel_info.data_type
                )

            target_channel_info = telemetry.get_channel(target_lambda_channel)
            if target_channel_info:
                target_values = self.units_manager.apply_channel_conversion(
                    target_lambda_channel, target_values, target_channel_info.data_type
                )

            actual_channel_info = telemetry.get_channel(actual_lambda_channel)
            if actual_channel_info:
                actual_values = self.units_manager.apply_channel_conversion(
                    actual_lambda_channel, actual_values, actual_channel_info.data_type
                )

            # Detect if values are in AFR format (typically 10-20) vs Lambda (0.5-2.0)
            valid_target = target_values[~np.isnan(target_values)]
            valid_actual = actual_values[~np.isnan(actual_values)]
            target_median = np.nanmedian(valid_target)
            actual_median = np.nanmedian(valid_actual[valid_actual > 0])  # Only positive values

            # Determine if data is in AFR format (>5) or Lambda format (<5)
            is_afr_format = target_median > 5 or actual_median > 5

            # Get stoichiometric ratio from user's AFR unit preference for conversion
            afr_pref = self.units_manager.unit_preferences.get('λ',
                       self.units_manager.default_preferences.get('λ', 'λ'))
            if 'E85' in afr_pref:
                stoich_ratio = 9.765  # E85
            elif 'Methanol' in afr_pref:
                stoich_ratio = 6.4  # Methanol
            else:
                stoich_ratio = 14.7  # Default to gasoline

            # Convert AFR to Lambda if data is in AFR format
            if is_afr_format:
                target_values = target_values / stoich_ratio
                actual_values = actual_values / stoich_ratio

            # Process samples
            samples_processed = 0
            samples_skipped_nan = 0
            samples_skipped_range = 0

            # Lambda range limits: ~0.6 (very rich) to ~1.5 (very lean)
            # (Values are already converted to Lambda if they were in AFR format)
            min_lambda, max_lambda = 0.6, 1.5

            for i in range(len(rpm_values)):
                rpm = rpm_values[i]
                load = load_values[i]
                target_lambda = target_values[i]
                actual_lambda = actual_values[i]

                # Skip invalid samples
                if np.isnan(rpm) or np.isnan(load) or np.isnan(target_lambda) or np.isnan(actual_lambda):
                    samples_skipped_nan += 1
                    continue

                # Sanity check lambda values
                if actual_lambda < min_lambda or actual_lambda > max_lambda:
                    samples_skipped_range += 1
                    continue
                if target_lambda < min_lambda or target_lambda > max_lambda:
                    samples_skipped_range += 1
                    continue

                # Find bin indices
                row_idx = find_bin_index(load, self.load_axis)
                col_idx = find_bin_index(rpm, self.rpm_axis)

                # Calculate correction ratio using Lambda formula
                # target / actual: if we're lean (actual > target), ratio < 1, need more fuel
                correction_ratio = target_lambda / actual_lambda
                binned_data[(row_idx, col_idx)].append(correction_ratio)

        return binned_data

    def _compute_corrections(self, binned_data: Dict[Tuple[int, int], List[float]],
                             min_samples: int):
        """Compute correction maps from binned data."""
        rows = len(self.load_axis)
        cols = len(self.rpm_axis)

        # Initialize maps
        self.hit_count_map = np.zeros((rows, cols), dtype=np.int32)
        self.error_map = np.full((rows, cols), np.nan)
        self.correction_map = np.ones((rows, cols), dtype=np.float32)
        self.corrected_ve_map = self.base_ve_map.copy()

        cells_with_data = 0
        for (row_idx, col_idx), ratios in binned_data.items():
            # Store hit count
            self.hit_count_map[row_idx, col_idx] = len(ratios)
            cells_with_data += 1

            if len(ratios) >= min_samples:
                # Calculate weighted average correction
                avg_correction = np.mean(ratios)

                # Calculate error (deviation from 1.0 = stoich)
                # Positive = running lean, needs more fuel
                # Negative = running rich, needs less fuel
                self.error_map[row_idx, col_idx] = (avg_correction - 1.0) * 100

                # Apply correction to base VE
                self.correction_map[row_idx, col_idx] = avg_correction
                self.corrected_ve_map[row_idx, col_idx] = \
                    self.base_ve_map[row_idx, col_idx] * avg_correction

    def _update_statistics(self):
        """Update statistics display."""
        if self.hit_count_map is not None:
            total_samples = int(np.sum(self.hit_count_map))
            cells_with_data = int(np.sum(self.hit_count_map > 0))
            total_cells = self.hit_count_map.size

            self.stats_total_label.setText(f"Samples: {total_samples:,}")
            self.stats_cells_label.setText(
                f"Cells: {cells_with_data}/{total_cells} ({100*cells_with_data/total_cells:.0f}%)"
            )

            if self.error_map is not None:
                valid_errors = self.error_map[~np.isnan(self.error_map)]
                if len(valid_errors) > 0:
                    max_error = np.max(np.abs(valid_errors))
                    self.stats_max_error_label.setText(f"Max err: {max_error:.1f}%")
                else:
                    self.stats_max_error_label.setText("Max err: -")

            if self.correction_map is not None:
                valid_corrections = self.correction_map[self.hit_count_map >= self.min_samples_spin.value()]
                if len(valid_corrections) > 0:
                    avg_correction = np.mean(valid_corrections)
                    self.stats_avg_correction_label.setText(f"Avg corr: {avg_correction:.3f}")
                else:
                    self.stats_avg_correction_label.setText("Avg corr: -")
        else:
            self.stats_total_label.setText("Samples: -")
            self.stats_cells_label.setText("Cells: -")
            self.stats_max_error_label.setText("Max err: -")
            self.stats_avg_correction_label.setText("Avg corr: -")

    def _save_corrected_map(self):
        """Save the corrected VE map to a file."""
        if self.corrected_ve_map is None:
            QMessageBox.warning(self, "No Data", "No corrected map to save. Calculate corrections first.")
            return

        config_dir = TabConfiguration.get_default_config_dir()

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Corrected VE Map",
            str(config_dir / "corrected_fuel_ve_map.csv"),
            "CSV Files (*.csv);;All Files (*.*)"
        )

        if not file_path:
            return

        # Ensure .csv extension
        if not file_path.endswith('.csv'):
            file_path += '.csv'

        success = VEMapManager.save_map(
            Path(file_path),
            self.corrected_ve_map,
            self.rpm_axis,
            self.load_axis,
            self.load_type
        )

        if success:
            QMessageBox.information(
                self,
                "Map Saved",
                f"Corrected VE map saved to:\n{file_path}"
            )
            self.status_label.setText(f"Saved: {Path(file_path).name}")
        else:
            QMessageBox.critical(
                self,
                "Save Error",
                "Failed to save the corrected map."
            )

    def _apply_dark_theme(self):
        """Apply dark theme styling to the dialog."""
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
            QTableWidget {
                background-color: #252526;
                border: 1px solid #3e3e42;
                border-radius: 3px;
                gridline-color: #1e1e1e;
                outline: none;
                selection-background-color: #094771;
                selection-color: #ffffff;
            }
            /* Note: QTableWidget::item not styled here - ColoredCellDelegate handles painting */
            QTableWidget QTableCornerButton::section {
                background-color: #333333;
                border: none;
                border-right: 1px solid #3e3e42;
                border-bottom: 1px solid #3e3e42;
            }
            QHeaderView::section {
                background-color: #333333;
                color: #dcdcdc;
                padding: 4px 6px;
                border: none;
                border-right: 1px solid #3e3e42;
                border-bottom: 1px solid #3e3e42;
                font-weight: bold;
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
            QPushButton:disabled {
                background-color: #3c3c3c;
                color: #666666;
            }
            QRadioButton {
                color: #dcdcdc;
                spacing: 8px;
            }
            QRadioButton::indicator {
                width: 14px;
                height: 14px;
                border-radius: 7px;
                border: 2px solid #3e3e42;
                background-color: #252526;
            }
            QRadioButton::indicator:checked {
                background-color: #007acc;
                border-color: #007acc;
            }
            QRadioButton::indicator:hover {
                border-color: #007acc;
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
            QDialogButtonBox {
                background-color: #1e1e1e;
            }
            QSplitter::handle {
                background-color: #3e3e42;
            }
            QSplitter::handle:horizontal {
                width: 2px;
            }
            QProgressDialog {
                background-color: #1e1e1e;
                color: #dcdcdc;
            }
        """)
