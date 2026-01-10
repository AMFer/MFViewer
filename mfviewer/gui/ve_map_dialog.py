"""
VE Map Calculator Dialog for calculating fuel VE corrections from telemetry data.

This dialog allows users to:
- Load a base VE map from CSV or paste from clipboard
- Analyze telemetry log data to calculate VE corrections
- Visualize cell usage (hit count) and lambda errors
- Save corrected VE maps
- Configure target AFR/Lambda tables
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
    QProgressDialog, QAbstractItemView, QStyledItemDelegate, QStyle,
    QTabWidget, QCheckBox, QApplication, QInputDialog, QMenu
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QBrush, QPalette, QShortcut, QKeySequence, QAction


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
from mfviewer.data.engine_model import EngineConfig, AlphaNModel, EngineConfigManager


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

        # Engine model for extrapolation
        self.engine_config: Optional[EngineConfig] = None
        self.ve_model: Optional[AlphaNModel] = None
        self.extrapolated_mask: Optional[np.ndarray] = None  # True = extrapolated cell

        # Target AFR/Lambda table
        self.target_afr_map: Optional[np.ndarray] = None
        self.target_rpm_axis: List[float] = []
        self.target_load_axis: List[float] = []

        # Persistent directories and paths for load/save
        self._last_load_dir: Optional[Path] = None
        self._last_save_dir: Optional[Path] = None
        self._last_ve_map_path: Optional[Path] = None  # Last loaded VE map file

        # Channel names discovered from logs
        self.available_channels: List[str] = []
        self._discover_channels()

        self.setWindowTitle("Fuel VE Map Calculator")
        self.setMinimumWidth(1600)
        self.setMinimumHeight(1050)
        self.resize(1800, 1150)

        # Make non-modal so user can interact with main window
        self.setWindowModality(Qt.WindowModality.NonModal)

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
                self.bins_only_checkbox.setChecked(settings.get('bins_only', False))

                # Load persistent directories
                if settings.get('last_load_dir'):
                    self._last_load_dir = Path(settings['last_load_dir'])
                    if not self._last_load_dir.exists():
                        self._last_load_dir = None
                if settings.get('last_save_dir'):
                    self._last_save_dir = Path(settings['last_save_dir'])
                    if not self._last_save_dir.exists():
                        self._last_save_dir = None

                # Load last VE map path
                if settings.get('last_ve_map_path'):
                    self._last_ve_map_path = Path(settings['last_ve_map_path'])
                    if not self._last_ve_map_path.exists():
                        self._last_ve_map_path = None

                # Load last engine config (handled separately in _load_engine_configs)
            except (json.JSONDecodeError, IOError):
                pass  # Use defaults if file is corrupted

    def _save_settings(self):
        """Save current settings to config file."""
        settings_file = self._get_settings_file()
        settings_file.parent.mkdir(parents=True, exist_ok=True)
        settings = {
            'min_samples': self.min_samples_spin.value(),
            'bins_only': self.bins_only_checkbox.isChecked(),
        }
        # Save persistent directories
        if self._last_load_dir:
            settings['last_load_dir'] = str(self._last_load_dir)
        if self._last_save_dir:
            settings['last_save_dir'] = str(self._last_save_dir)
        # Save last VE map path
        if self._last_ve_map_path:
            settings['last_ve_map_path'] = str(self._last_ve_map_path)
        # Save last engine config
        current_engine = self.engine_combo.currentText()
        if current_engine and current_engine != "-- Select Engine --":
            settings['last_engine_config'] = current_engine
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

        self.save_map_btn = QPushButton("Save VE Map...")
        self.save_map_btn.clicked.connect(self._save_corrected_map)
        self.save_map_btn.setEnabled(False)  # Enabled when a map is loaded
        toolbar_layout.addWidget(self.save_map_btn)

        self.copy_map_btn = QPushButton("Copy to Clipboard")
        self.copy_map_btn.clicked.connect(self._copy_map_to_clipboard)
        self.copy_map_btn.setEnabled(False)
        self.copy_map_btn.setToolTip("Copy corrected VE values to clipboard (no row/column labels)")
        toolbar_layout.addWidget(self.copy_map_btn)

        self.paste_map_btn = QPushButton("Paste from Clipboard")
        self.paste_map_btn.clicked.connect(self._paste_map_from_clipboard)
        self.paste_map_btn.setToolTip("Paste VE map with headers (first row = RPM, first column = Load)")
        toolbar_layout.addWidget(self.paste_map_btn)

        self.paste_ve_only_btn = QPushButton("Paste VE Only")
        self.paste_ve_only_btn.clicked.connect(self._paste_ve_only_from_clipboard)
        self.paste_ve_only_btn.setToolTip("Paste only VE values from clipboard, keeping current RPM/Load axes")
        self.paste_ve_only_btn.setEnabled(False)  # Enable only when a map is loaded
        toolbar_layout.addWidget(self.paste_ve_only_btn)

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

        # Left side - Tab widget with map tables
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # Tab widget for VE Map and Target AFR tables
        self.table_tabs = QTabWidget()

        # VE Map tab
        ve_tab = QWidget()
        ve_tab_layout = QVBoxLayout(ve_tab)
        ve_tab_layout.setContentsMargins(4, 4, 4, 4)

        self.map_table = QTableWidget()
        self.map_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.map_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.map_table.cellClicked.connect(self._on_cell_clicked)
        self.map_table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        # Use custom delegate to paint background colors (overrides stylesheet)
        self.map_table.setItemDelegate(ColoredCellDelegate(self.map_table))
        ve_tab_layout.addWidget(self.map_table)

        # Cell info label for VE table
        self.cell_info_label = QLabel("")
        self.cell_info_label.setStyleSheet("color: #cccccc; padding: 4px;")
        ve_tab_layout.addWidget(self.cell_info_label)

        self.table_tabs.addTab(ve_tab, "VE Map")

        # Target AFR/Lambda tab
        target_tab = QWidget()
        target_tab_layout = QVBoxLayout(target_tab)
        target_tab_layout.setContentsMargins(4, 4, 4, 4)

        # Toolbar for target map
        target_toolbar = QHBoxLayout()
        self.load_target_btn = QPushButton("Load Target Map...")
        self.load_target_btn.clicked.connect(self._load_target_map_dialog)
        target_toolbar.addWidget(self.load_target_btn)

        self.paste_target_btn = QPushButton("Paste from Clipboard")
        self.paste_target_btn.clicked.connect(self._paste_target_from_clipboard)
        target_toolbar.addWidget(self.paste_target_btn)

        self.copy_target_btn = QPushButton("Copy to Clipboard")
        self.copy_target_btn.clicked.connect(self._copy_target_to_clipboard)
        self.copy_target_btn.setEnabled(False)
        target_toolbar.addWidget(self.copy_target_btn)

        target_toolbar.addStretch()

        # Lambda/AFR selector for target display
        target_toolbar.addWidget(QLabel("Display:"))
        self.target_display_combo = QComboBox()
        self.target_display_combo.addItems(["Lambda", "AFR (Gasoline)", "AFR (E85)"])
        self.target_display_combo.currentTextChanged.connect(self._update_target_display)
        target_toolbar.addWidget(self.target_display_combo)

        target_tab_layout.addLayout(target_toolbar)

        self.target_table = QTableWidget()
        self.target_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.target_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.target_table.cellClicked.connect(self._on_target_cell_clicked)
        target_tab_layout.addWidget(self.target_table)

        # Cell info label for target table
        self.target_cell_info_label = QLabel("Load a target AFR/Lambda map or paste from clipboard")
        self.target_cell_info_label.setStyleSheet("color: #888888; padding: 4px; font-style: italic;")
        target_tab_layout.addWidget(self.target_cell_info_label)

        self.table_tabs.addTab(target_tab, "Target AFR/Lambda")

        left_layout.addWidget(self.table_tabs)

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

        self.view_proposed_radio = QRadioButton("Proposed VE Values")
        self.view_mode_group.addButton(self.view_proposed_radio, 3)
        view_layout.addWidget(self.view_proposed_radio)

        self.view_mode_group.buttonClicked.connect(self._on_view_mode_changed)

        view_group.setLayout(view_layout)
        right_layout.addWidget(view_group)

        # Settings
        settings_group = QGroupBox("Settings")
        settings_layout = QVBoxLayout()
        settings_layout.setSpacing(4)

        min_samples_row = QHBoxLayout()
        min_samples_row.addWidget(QLabel("Min Samples:"))
        self.min_samples_spin = QSpinBox()
        self.min_samples_spin.setRange(1, 1000)
        self.min_samples_spin.setValue(10)
        self.min_samples_spin.setToolTip("Minimum samples required to calculate a correction for a cell")
        self.min_samples_spin.valueChanged.connect(self._save_settings)
        min_samples_row.addWidget(self.min_samples_spin)
        settings_layout.addLayout(min_samples_row)

        self.bins_only_checkbox = QCheckBox("Bins only (no correction)")
        self.bins_only_checkbox.setToolTip("Only determine which bins are hit, don't apply corrections")
        self.bins_only_checkbox.stateChanged.connect(self._save_settings)
        self.bins_only_checkbox.stateChanged.connect(self._on_bins_only_changed)
        settings_layout.addWidget(self.bins_only_checkbox)

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

        # Model Fitting group
        model_group = QGroupBox("Model Fitting")
        model_layout = QVBoxLayout()
        model_layout.setSpacing(4)

        # Engine profile selector
        engine_row = QHBoxLayout()
        engine_row.addWidget(QLabel("Engine:"))
        self.engine_combo = QComboBox()
        self.engine_combo.setMinimumWidth(100)
        self.engine_combo.currentTextChanged.connect(self._on_engine_selected)
        engine_row.addWidget(self.engine_combo, 1)
        model_layout.addLayout(engine_row)

        # Configure button
        self.config_engine_btn = QPushButton("Configure Engine...")
        self.config_engine_btn.clicked.connect(self._open_engine_config)
        model_layout.addWidget(self.config_engine_btn)

        # Fit model button
        self.fit_model_btn = QPushButton("Fit Model")
        self.fit_model_btn.clicked.connect(self._fit_model)
        self.fit_model_btn.setEnabled(False)
        model_layout.addWidget(self.fit_model_btn)

        # Fit statistics labels
        self.fit_r2_label = QLabel("R\u00b2: -")
        self.fit_r2_label.setStyleSheet("color: #aaaaaa;")
        model_layout.addWidget(self.fit_r2_label)

        self.fit_rmse_label = QLabel("RMSE: -")
        self.fit_rmse_label.setStyleSheet("color: #aaaaaa;")
        model_layout.addWidget(self.fit_rmse_label)

        # Fill empty cells button
        self.fill_cells_btn = QPushButton("Fill Empty Cells")
        self.fill_cells_btn.clicked.connect(self._fill_empty_cells)
        self.fill_cells_btn.setEnabled(False)
        self.fill_cells_btn.setToolTip("Use fitted model to extrapolate empty cells")
        model_layout.addWidget(self.fill_cells_btn)

        # Cell counts
        self.measured_cells_label = QLabel("Measured: -")
        self.measured_cells_label.setStyleSheet("color: #aaaaaa;")
        model_layout.addWidget(self.measured_cells_label)

        self.extrapolated_cells_label = QLabel("Extrapolated: -")
        self.extrapolated_cells_label.setStyleSheet("color: #6ab0de;")  # Light blue
        model_layout.addWidget(self.extrapolated_cells_label)

        model_group.setLayout(model_layout)
        right_layout.addWidget(model_group)

        # Populate engine combo
        self._load_engine_configs()

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
        """Load the default base map or last used map."""
        # Try to load last used VE map first
        if self._last_ve_map_path and self._last_ve_map_path.exists():
            self._load_map(self._last_ve_map_path)
        else:
            # Fall back to default map
            default_path = self.ve_map_manager.get_default_map_path()
            if default_path.exists():
                self._load_map(default_path)

    def _load_map_dialog(self):
        """Show file dialog to load a base map."""
        # Use persistent directory if available, then last VE map's directory, then default
        if self._last_load_dir and self._last_load_dir.exists():
            default_path = self._last_load_dir
        elif self._last_ve_map_path and self._last_ve_map_path.parent.exists():
            default_path = self._last_ve_map_path.parent
        else:
            default_path = self.ve_map_manager.get_default_map_path().parent

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Base VE Map",
            str(default_path),
            "CSV Files (*.csv);;All Files (*.*)"
        )

        if file_path:
            # Save the directory for next time
            self._last_load_dir = Path(file_path).parent
            self._save_settings()
            self._load_map(Path(file_path))

    def _load_map(self, file_path: Path):
        """Load a VE map from file."""
        try:
            self.base_ve_map, self.rpm_axis, self.load_axis, self.load_type = \
                VEMapManager.load_map(file_path)

            # Save the path for next time
            self._last_ve_map_path = file_path
            self._save_settings()

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
            self.save_map_btn.setEnabled(True)
            self.paste_ve_only_btn.setEnabled(True)

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
        # Connect double-click for editing column headers
        header.sectionDoubleClicked.connect(self._edit_column_header)
        # Enable context menu for column operations
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self._show_column_context_menu)

        # Set rows to have consistent height
        vert_header = self.map_table.verticalHeader()
        vert_header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        # Connect double-click for editing row headers
        vert_header.sectionDoubleClicked.connect(self._edit_row_header)
        # Enable context menu for row operations
        vert_header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        vert_header.customContextMenuRequested.connect(self._show_row_context_menu)

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
                elif self.view_mode == "error":
                    text, color = self._get_error_display(row, col, base_ve)
                else:  # proposed
                    text, color = self._get_proposed_display(row, col, base_ve)

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
        # Check if this is an extrapolated cell
        is_extrapolated = (self.extrapolated_mask is not None and
                          self.extrapolated_mask[row, col])

        # Check if bins-only mode is active
        bins_only = self.bins_only_checkbox.isChecked()
        min_samples = self.min_samples_spin.value()

        if self.corrected_ve_map is not None:
            new_ve = self.corrected_ve_map[row, col]
            correction = self.correction_map[row, col] if self.correction_map is not None else 1.0

            if correction != 1.0:
                change_pct = (correction - 1.0) * 100
                text = f"{base_ve:.1f}→{new_ve:.1f}"

                if is_extrapolated:
                    # Blue tint for extrapolated cells
                    color = self._get_extrapolated_color(change_pct)
                else:
                    color = self._get_correction_color(change_pct)
            elif bins_only and self.hit_count_map is not None:
                # In bins-only mode, highlight cells that have data
                hit_count = self.hit_count_map[row, col]
                if hit_count >= min_samples:
                    # Cell has sufficient data - highlight with cyan/teal
                    text = f"{base_ve:.1f}"
                    color = QColor(50, 120, 120)  # Teal - measured but no correction applied
                elif hit_count > 0:
                    # Cell has some data but not enough - dim highlight
                    text = f"{base_ve:.1f}"
                    color = QColor(50, 80, 80)  # Darker teal - insufficient samples
                else:
                    text = f"{base_ve:.1f}"
                    color = QColor(60, 60, 70)
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

    def _get_extrapolated_color(self, change_pct: float) -> QColor:
        """Get color for extrapolated cells. Blue-tinted versions of correction colors."""
        # Blue-tinted colors to distinguish extrapolated from measured
        if abs(change_pct) < 1.0:
            return QColor(50, 60, 80)  # Minor change - blue-gray
        elif abs(change_pct) < 3.0:
            if change_pct > 0:
                return QColor(100, 80, 130)  # Small increase - purple-blue
            else:
                return QColor(60, 100, 130)  # Small decrease - teal-blue
        elif abs(change_pct) < 7.0:
            if change_pct > 0:
                return QColor(120, 90, 160)  # Medium increase - purple
            else:
                return QColor(70, 120, 160)  # Medium decrease - cyan-blue
        else:
            if change_pct > 0:
                return QColor(140, 100, 180)  # Large increase - bright purple
            else:
                return QColor(80, 140, 180)  # Large decrease - bright cyan

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

    def _get_proposed_display(self, row: int, col: int, base_ve: float) -> Tuple[str, QColor]:
        """Get display text and color for proposed VE values view."""
        # Check if this is an extrapolated cell
        is_extrapolated = (self.extrapolated_mask is not None and
                          self.extrapolated_mask[row, col])

        if self.corrected_ve_map is not None:
            new_ve = self.corrected_ve_map[row, col]
            text = f"{new_ve:.1f}"

            # Color based on whether value changed and if extrapolated
            if is_extrapolated:
                color = QColor(70, 100, 150)  # Blue for extrapolated
            elif abs(new_ve - base_ve) > 0.1:
                color = QColor(80, 130, 80)  # Green for measured correction
            else:
                color = QColor(60, 60, 70)  # Gray for unchanged
        else:
            text = f"{base_ve:.1f}"
            color = QColor(60, 60, 70)

        return text, color

    def _update_legend(self):
        """Update the color legend based on current view mode."""
        bins_only = self.bins_only_checkbox.isChecked()

        if self.view_mode == "correction":
            if bins_only:
                # Show bins-only legend
                legends = [
                    ("No data", QColor(60, 60, 70)),
                    ("Insufficient samples", QColor(50, 80, 80)),
                    ("Measured (bins only)", QColor(50, 120, 120)),
                    ("", QColor(30, 30, 30)),  # Empty placeholder
                    ("", QColor(30, 30, 30)),  # Empty placeholder
                ]
            else:
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
        elif self.view_mode == "error":
            legends = [
                ("On target (<2%)", QColor(60, 180, 80)),
                ("Slight error (2-5%)", QColor(200, 200, 60)),
                ("Moderate error (5-10%)", QColor(230, 150, 50)),
                ("Large lean (>10%)", QColor(230, 70, 70)),
                ("Large rich (>10%)", QColor(70, 100, 230)),
            ]
        else:  # proposed
            legends = [
                ("Unchanged", QColor(60, 60, 70)),
                ("Measured correction", QColor(80, 130, 80)),
                ("Extrapolated", QColor(70, 100, 150)),
                ("", QColor(30, 30, 30)),  # Empty placeholder
                ("", QColor(30, 30, 30)),  # Empty placeholder
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
        elif button_id == 2:
            self.view_mode = "error"
        else:
            self.view_mode = "proposed"

        self._update_map_display()
        self._update_legend()

    def _on_bins_only_changed(self, state: int):
        """Handle bins-only checkbox toggle."""
        # Update display and legend to reflect the new mode
        if self.base_ve_map is not None:
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

    def _edit_column_header(self, col: int):
        """Edit column header (RPM value) via double-click."""
        if not self.rpm_axis or col >= len(self.rpm_axis):
            return

        current_value = self.rpm_axis[col]

        value, ok = QInputDialog.getDouble(
            self,
            "Edit RPM Value",
            f"Enter new RPM value for column {col + 1}:",
            current_value,
            0,  # min
            20000,  # max
            0  # decimals
        )

        if ok:
            # Update the axis value
            self.rpm_axis[col] = value
            # Update table header
            self.map_table.setHorizontalHeaderItem(
                col, QTableWidgetItem(str(int(value)))
            )
            self.status_label.setText(f"Updated RPM column {col + 1} to {int(value)}")
            self.status_label.setStyleSheet("color: #4ec9b0;")

    def _edit_row_header(self, row: int):
        """Edit row header (Load/TPS value) via double-click."""
        if not self.load_axis or row >= len(self.load_axis):
            return

        current_value = self.load_axis[row]

        value, ok = QInputDialog.getDouble(
            self,
            "Edit Load Value",
            f"Enter new Load/TPS value for row {row + 1}:",
            current_value,
            0,  # min
            120,  # max
            1  # decimals
        )

        if ok:
            # Update the axis value
            self.load_axis[row] = value
            # Update table header
            self.map_table.setVerticalHeaderItem(
                row, QTableWidgetItem(f"{value:.0f}%")
            )
            self.status_label.setText(f"Updated Load row {row + 1} to {value:.0f}%")
            self.status_label.setStyleSheet("color: #4ec9b0;")

    def _show_column_context_menu(self, pos):
        """Show context menu for column (RPM) header operations."""
        header = self.map_table.horizontalHeader()
        col = header.logicalIndexAt(pos)
        if col < 0 or self.base_ve_map is None:
            return

        menu = QMenu(self)

        # Insert actions
        insert_before = QAction(f"Insert Column Before ({int(self.rpm_axis[col])} RPM)", self)
        insert_before.triggered.connect(lambda: self._insert_column(col))
        menu.addAction(insert_before)

        insert_after = QAction(f"Insert Column After ({int(self.rpm_axis[col])} RPM)", self)
        insert_after.triggered.connect(lambda: self._insert_column(col + 1))
        menu.addAction(insert_after)

        menu.addSeparator()

        # Delete action
        delete_col = QAction(f"Delete Column ({int(self.rpm_axis[col])} RPM)", self)
        delete_col.triggered.connect(lambda: self._delete_column(col))
        # Disable if only one column remains
        if self.base_ve_map.shape[1] <= 1:
            delete_col.setEnabled(False)
        menu.addAction(delete_col)

        menu.exec(header.mapToGlobal(pos))

    def _show_row_context_menu(self, pos):
        """Show context menu for row (Load/TPS) header operations."""
        header = self.map_table.verticalHeader()
        row = header.logicalIndexAt(pos)
        if row < 0 or self.base_ve_map is None:
            return

        menu = QMenu(self)

        # Insert actions
        insert_before = QAction(f"Insert Row Before ({self.load_axis[row]:.0f}%)", self)
        insert_before.triggered.connect(lambda: self._insert_row(row))
        menu.addAction(insert_before)

        insert_after = QAction(f"Insert Row After ({self.load_axis[row]:.0f}%)", self)
        insert_after.triggered.connect(lambda: self._insert_row(row + 1))
        menu.addAction(insert_after)

        menu.addSeparator()

        # Delete action
        delete_row = QAction(f"Delete Row ({self.load_axis[row]:.0f}%)", self)
        delete_row.triggered.connect(lambda: self._delete_row(row))
        # Disable if only one row remains
        if self.base_ve_map.shape[0] <= 1:
            delete_row.setEnabled(False)
        menu.addAction(delete_row)

        menu.exec(header.mapToGlobal(pos))

    def _insert_column(self, col: int):
        """Insert a new column (RPM breakpoint) at the specified index."""
        if self.base_ve_map is None:
            return

        # Determine the new RPM value
        if col == 0:
            # Insert before first column
            new_rpm = self.rpm_axis[0] - 500 if self.rpm_axis[0] > 500 else 0
        elif col >= len(self.rpm_axis):
            # Insert after last column
            new_rpm = self.rpm_axis[-1] + 500
        else:
            # Insert between columns - use midpoint
            new_rpm = (self.rpm_axis[col - 1] + self.rpm_axis[col]) / 2

        # Prompt user for the RPM value
        value, ok = QInputDialog.getDouble(
            self,
            "Insert Column",
            "Enter RPM value for new column:",
            new_rpm,
            0,  # min
            20000,  # max
            0  # decimals
        )

        if not ok:
            return

        # Insert into RPM axis
        self.rpm_axis.insert(col, value)

        # Insert column into all map arrays
        # Use interpolation between neighboring columns for initial values
        rows = self.base_ve_map.shape[0]

        if col == 0:
            # Copy from first column
            new_col = self.base_ve_map[:, 0:1].copy()
        elif col >= self.base_ve_map.shape[1]:
            # Copy from last column
            new_col = self.base_ve_map[:, -1:].copy()
        else:
            # Interpolate between neighboring columns
            left_col = self.base_ve_map[:, col - 1:col]
            right_col = self.base_ve_map[:, col:col + 1]
            new_col = (left_col + right_col) / 2

        self.base_ve_map = np.insert(self.base_ve_map, col, new_col.flatten(), axis=1)

        # Update other maps if they exist
        if self.corrected_ve_map is not None:
            if col == 0:
                new_col = self.corrected_ve_map[:, 0:1].copy()
            elif col >= self.corrected_ve_map.shape[1]:
                new_col = self.corrected_ve_map[:, -1:].copy()
            else:
                new_col = (self.corrected_ve_map[:, col - 1:col] + self.corrected_ve_map[:, col:col + 1]) / 2
            self.corrected_ve_map = np.insert(self.corrected_ve_map, col, new_col.flatten(), axis=1)

        if self.hit_count_map is not None:
            self.hit_count_map = np.insert(self.hit_count_map, col, np.zeros(rows), axis=1)

        if self.error_map is not None:
            self.error_map = np.insert(self.error_map, col, np.zeros(rows), axis=1)

        if self.correction_map is not None:
            self.correction_map = np.insert(self.correction_map, col, np.ones(rows), axis=1)

        if self.extrapolated_mask is not None:
            self.extrapolated_mask = np.insert(self.extrapolated_mask, col, np.zeros(rows, dtype=bool), axis=1)

        # Rebuild the table
        self._setup_map_table()
        self._update_map_display()

        self.status_label.setText(f"Inserted column at {int(value)} RPM")
        self.status_label.setStyleSheet("color: #4ec9b0;")

    def _insert_row(self, row: int):
        """Insert a new row (Load/TPS breakpoint) at the specified index."""
        if self.base_ve_map is None:
            return

        # Determine the new Load value
        if row == 0:
            # Insert before first row
            new_load = self.load_axis[0] - 5 if self.load_axis[0] > 5 else 0
        elif row >= len(self.load_axis):
            # Insert after last row
            new_load = min(self.load_axis[-1] + 5, 100)
        else:
            # Insert between rows - use midpoint
            new_load = (self.load_axis[row - 1] + self.load_axis[row]) / 2

        # Prompt user for the Load value
        value, ok = QInputDialog.getDouble(
            self,
            "Insert Row",
            "Enter Load/TPS value for new row (%):",
            new_load,
            0,  # min
            120,  # max
            1  # decimals
        )

        if not ok:
            return

        # Insert into Load axis
        self.load_axis.insert(row, value)

        # Insert row into all map arrays
        cols = self.base_ve_map.shape[1]

        if row == 0:
            # Copy from first row
            new_row = self.base_ve_map[0:1, :].copy()
        elif row >= self.base_ve_map.shape[0]:
            # Copy from last row
            new_row = self.base_ve_map[-1:, :].copy()
        else:
            # Interpolate between neighboring rows
            top_row = self.base_ve_map[row - 1:row, :]
            bottom_row = self.base_ve_map[row:row + 1, :]
            new_row = (top_row + bottom_row) / 2

        self.base_ve_map = np.insert(self.base_ve_map, row, new_row.flatten(), axis=0)

        # Update other maps if they exist
        if self.corrected_ve_map is not None:
            if row == 0:
                new_row = self.corrected_ve_map[0:1, :].copy()
            elif row >= self.corrected_ve_map.shape[0]:
                new_row = self.corrected_ve_map[-1:, :].copy()
            else:
                new_row = (self.corrected_ve_map[row - 1:row, :] + self.corrected_ve_map[row:row + 1, :]) / 2
            self.corrected_ve_map = np.insert(self.corrected_ve_map, row, new_row.flatten(), axis=0)

        if self.hit_count_map is not None:
            self.hit_count_map = np.insert(self.hit_count_map, row, np.zeros(cols), axis=0)

        if self.error_map is not None:
            self.error_map = np.insert(self.error_map, row, np.zeros(cols), axis=0)

        if self.correction_map is not None:
            self.correction_map = np.insert(self.correction_map, row, np.ones(cols), axis=0)

        if self.extrapolated_mask is not None:
            self.extrapolated_mask = np.insert(self.extrapolated_mask, row, np.zeros(cols, dtype=bool), axis=0)

        # Rebuild the table
        self._setup_map_table()
        self._update_map_display()

        self.status_label.setText(f"Inserted row at {value:.0f}%")
        self.status_label.setStyleSheet("color: #4ec9b0;")

    def _delete_column(self, col: int):
        """Delete a column (RPM breakpoint) at the specified index."""
        if self.base_ve_map is None or self.base_ve_map.shape[1] <= 1:
            return

        rpm_value = self.rpm_axis[col]

        # Confirm deletion
        reply = QMessageBox.question(
            self,
            "Delete Column",
            f"Delete column at {int(rpm_value)} RPM?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Remove from RPM axis
        del self.rpm_axis[col]

        # Remove column from all map arrays
        self.base_ve_map = np.delete(self.base_ve_map, col, axis=1)

        if self.corrected_ve_map is not None:
            self.corrected_ve_map = np.delete(self.corrected_ve_map, col, axis=1)

        if self.hit_count_map is not None:
            self.hit_count_map = np.delete(self.hit_count_map, col, axis=1)

        if self.error_map is not None:
            self.error_map = np.delete(self.error_map, col, axis=1)

        if self.correction_map is not None:
            self.correction_map = np.delete(self.correction_map, col, axis=1)

        if self.extrapolated_mask is not None:
            self.extrapolated_mask = np.delete(self.extrapolated_mask, col, axis=1)

        # Rebuild the table
        self._setup_map_table()
        self._update_map_display()

        self.status_label.setText(f"Deleted column at {int(rpm_value)} RPM")
        self.status_label.setStyleSheet("color: #4ec9b0;")

    def _delete_row(self, row: int):
        """Delete a row (Load/TPS breakpoint) at the specified index."""
        if self.base_ve_map is None or self.base_ve_map.shape[0] <= 1:
            return

        load_value = self.load_axis[row]

        # Confirm deletion
        reply = QMessageBox.question(
            self,
            "Delete Row",
            f"Delete row at {load_value:.0f}%?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Remove from Load axis
        del self.load_axis[row]

        # Remove row from all map arrays
        self.base_ve_map = np.delete(self.base_ve_map, row, axis=0)

        if self.corrected_ve_map is not None:
            self.corrected_ve_map = np.delete(self.corrected_ve_map, row, axis=0)

        if self.hit_count_map is not None:
            self.hit_count_map = np.delete(self.hit_count_map, row, axis=0)

        if self.error_map is not None:
            self.error_map = np.delete(self.error_map, row, axis=0)

        if self.correction_map is not None:
            self.correction_map = np.delete(self.correction_map, row, axis=0)

        if self.extrapolated_mask is not None:
            self.extrapolated_mask = np.delete(self.extrapolated_mask, row, axis=0)

        # Rebuild the table
        self._setup_map_table()
        self._update_map_display()

        self.status_label.setText(f"Deleted row at {load_value:.0f}%")
        self.status_label.setStyleSheet("color: #4ec9b0;")

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
            self.copy_map_btn.setEnabled(True)

            # Update model fitting UI (enables Fit button if engine is selected)
            self._update_model_ui()

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
                # actual / target: if we're lean (actual > target), ratio > 1, need more fuel (higher VE)
                # if we're rich (actual < target), ratio < 1, need less fuel (lower VE)
                correction_ratio = actual_lambda / target_lambda
                binned_data[(row_idx, col_idx)].append(correction_ratio)

        return binned_data

    def _compute_corrections(self, binned_data: Dict[Tuple[int, int], List[float]],
                             min_samples: int):
        """Compute correction maps from binned data."""
        rows = len(self.load_axis)
        cols = len(self.rpm_axis)

        # Check if bins-only mode is enabled
        bins_only = self.bins_only_checkbox.isChecked()

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

                # Only apply correction if not in bins-only mode
                if not bins_only:
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
        """Save the VE map to a file (corrected if available, otherwise base map)."""
        if self.base_ve_map is None:
            QMessageBox.warning(self, "No Data", "No VE map to save. Load a map first.")
            return

        # Use corrected map if available, otherwise use base map
        map_to_save = self.corrected_ve_map if self.corrected_ve_map is not None else self.base_ve_map
        is_corrected = self.corrected_ve_map is not None

        # Use persistent directory if available, then last VE map's directory, then default
        if self._last_save_dir and self._last_save_dir.exists():
            default_path = self._last_save_dir / "fuel_ve_map.csv"
        elif self._last_ve_map_path and self._last_ve_map_path.parent.exists():
            default_path = self._last_ve_map_path.parent / "fuel_ve_map.csv"
        else:
            default_path = TabConfiguration.get_default_config_dir() / "fuel_ve_map.csv"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save VE Map",
            str(default_path),
            "CSV Files (*.csv);;All Files (*.*)"
        )

        if not file_path:
            return

        # Save the directory for next time
        self._last_save_dir = Path(file_path).parent
        self._save_settings()

        # Ensure .csv extension
        if not file_path.endswith('.csv'):
            file_path += '.csv'

        success = VEMapManager.save_map(
            Path(file_path),
            map_to_save,
            self.rpm_axis,
            self.load_axis,
            self.load_type
        )

        if success:
            map_type = "Corrected VE" if is_corrected else "VE"
            QMessageBox.information(
                self,
                "Map Saved",
                f"{map_type} map saved to:\n{file_path}"
            )
            self.status_label.setText(f"Saved: {Path(file_path).name}")
        else:
            QMessageBox.critical(
                self,
                "Save Error",
                "Failed to save the VE map."
            )

    def _copy_map_to_clipboard(self):
        """Copy the corrected VE map values to clipboard (no row/column labels)."""
        if self.corrected_ve_map is None:
            return

        # Build tab-separated values string (no headers)
        lines = []
        rows, cols = self.corrected_ve_map.shape
        for row in range(rows):
            row_values = [f"{self.corrected_ve_map[row, col]:.1f}" for col in range(cols)]
            lines.append("\t".join(row_values))

        clipboard_text = "\n".join(lines)

        # Copy to clipboard
        from PyQt6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(clipboard_text)

        self.status_label.setText("Copied to clipboard")
        self.status_label.setStyleSheet("color: #4ec9b0;")

    def _paste_map_from_clipboard(self):
        """Paste VE map from clipboard.

        Expects format with first row as RPM headers and first column as Load headers.
        First cell (top-left) is ignored (typically a label or empty).
        """
        clipboard = QApplication.clipboard()
        text = clipboard.text()

        if not text.strip():
            QMessageBox.warning(self, "Empty Clipboard", "No data found in clipboard.")
            return

        try:
            # Parse clipboard text (supports tab or comma separated)
            lines = text.strip().split('\n')
            rows_data = []

            for line in lines:
                # Try tab first, then comma
                if '\t' in line:
                    cells = line.split('\t')
                else:
                    cells = line.split(',')
                # Strip whitespace from each cell
                cells = [c.strip() for c in cells]
                if cells:  # Skip empty lines
                    rows_data.append(cells)

            if not rows_data or len(rows_data) < 2:
                QMessageBox.warning(self, "Parse Error", "Need at least 2 rows (header + data).")
                return

            if len(rows_data[0]) < 2:
                QMessageBox.warning(self, "Parse Error", "Need at least 2 columns (header + data).")
                return

            # First row is RPM headers (skip first cell which is a label)
            rpm_axis = self._parse_numeric_row(rows_data[0][1:])

            # First column (rows 1+) is Load headers, remaining cells are VE data
            load_axis = []
            ve_data = []
            for row in rows_data[1:]:
                if row:
                    load_axis.append(self._parse_numeric_value(row[0]))
                    ve_data.append(self._parse_numeric_row(row[1:]))

            # Validate dimensions
            if not ve_data or not ve_data[0]:
                QMessageBox.warning(self, "Parse Error", "No valid data found in clipboard.")
                return

            n_rows = len(ve_data)
            n_cols = len(ve_data[0])

            # Ensure all rows have same number of columns
            for i, row in enumerate(ve_data):
                if len(row) != n_cols:
                    QMessageBox.warning(
                        self, "Parse Error",
                        f"Row {i+1} has {len(row)} columns, expected {n_cols}."
                    )
                    return

            # Validate axis lengths match data dimensions
            if len(rpm_axis) != n_cols:
                QMessageBox.warning(
                    self, "Parse Error",
                    f"RPM header has {len(rpm_axis)} values but data has {n_cols} columns."
                )
                return
            if len(load_axis) != n_rows:
                QMessageBox.warning(
                    self, "Parse Error",
                    f"Load header has {len(load_axis)} values but data has {n_rows} rows."
                )
                return

            # Convert to numpy array
            self.base_ve_map = np.array(ve_data, dtype=np.float64)
            self.rpm_axis = rpm_axis
            self.load_axis = load_axis
            self.load_type = "TPS"  # Default

            # Reset correction data
            self.corrected_ve_map = None
            self.hit_count_map = None
            self.error_map = None
            self.correction_map = None
            self.extrapolated_mask = None

            # Update UI
            self._setup_map_table()
            self._update_map_display()
            self._update_statistics()

            self.status_label.setText(f"Pasted {n_rows}x{n_cols} map with headers")
            self.status_label.setStyleSheet("color: #4ec9b0;")
            self.calculate_btn.setEnabled(self.log_manager.get_main_log() is not None)
            self.save_map_btn.setEnabled(True)
            self.paste_ve_only_btn.setEnabled(True)

        except Exception as e:
            QMessageBox.critical(
                self, "Paste Error",
                f"Failed to parse clipboard data:\n{e}"
            )

    def _paste_ve_only_from_clipboard(self):
        """Paste only VE values from clipboard, keeping current RPM/Load axes."""
        if self.base_ve_map is None:
            QMessageBox.warning(self, "No Map", "Please load a base map first.")
            return

        clipboard = QApplication.clipboard()
        text = clipboard.text()

        if not text.strip():
            QMessageBox.warning(self, "Empty Clipboard", "No data found in clipboard.")
            return

        try:
            # Parse clipboard text (supports tab or comma separated)
            lines = text.strip().split('\n')
            rows_data = []

            for line in lines:
                # Try tab first, then comma
                if '\t' in line:
                    cells = line.split('\t')
                else:
                    cells = line.split(',')
                # Strip whitespace from each cell
                cells = [c.strip() for c in cells]
                if cells:  # Skip empty lines
                    rows_data.append(cells)

            if not rows_data:
                QMessageBox.warning(self, "Parse Error", "Could not parse clipboard data.")
                return

            # For "Paste VE Only", treat all data as VE values - no header detection
            # User explicitly wants just the values, not axes
            ve_data = [self._parse_numeric_row(row) for row in rows_data]

            if not ve_data or not ve_data[0]:
                QMessageBox.warning(self, "Parse Error", "No valid data found in clipboard.")
                return

            n_rows = len(ve_data)
            n_cols = len(ve_data[0])

            # Check dimensions match current map
            current_rows, current_cols = self.base_ve_map.shape

            if n_rows != current_rows or n_cols != current_cols:
                QMessageBox.warning(
                    self, "Size Mismatch",
                    f"Clipboard data is {n_rows}x{n_cols}, but current map is {current_rows}x{current_cols}.\n\n"
                    f"Use 'Paste from Clipboard' to replace the entire map including axes."
                )
                return

            # Ensure all rows have same number of columns
            for i, row in enumerate(ve_data):
                if len(row) != n_cols:
                    QMessageBox.warning(
                        self, "Parse Error",
                        f"Row {i+1} has {len(row)} columns, expected {n_cols}."
                    )
                    return

            # Update only the VE values, keep axes
            self.base_ve_map = np.array(ve_data, dtype=np.float64)

            # Clear calculated data since base map changed
            self.corrected_ve_map = None
            self.hit_count_map = None
            self.error_map = None
            self.correction_map = None
            self.extrapolated_mask = None
            self.ve_model = None

            # Update display
            self._update_map_display()
            self._update_statistics()
            self._update_legend()

            self.status_label.setText(f"Pasted {n_rows}x{n_cols} VE values (axes unchanged)")
            self.status_label.setStyleSheet("color: #4ec9b0;")
            self.calculate_btn.setEnabled(self.log_manager.get_main_log() is not None)
            self.save_map_btn.setEnabled(True)

        except Exception as e:
            QMessageBox.critical(
                self, "Paste Error",
                f"Failed to parse clipboard data:\n{e}"
            )

    def _detect_rpm_header(self, first_row: List[str]) -> bool:
        """Detect if the first row contains RPM values (numeric, generally increasing)."""
        if not first_row:
            return False

        # Skip first cell if it might be a label (non-numeric or contains text)
        start_idx = 0
        if first_row[0] and not self._is_numeric(first_row[0]):
            start_idx = 1

        if len(first_row) - start_idx < 3:
            return False

        # Check if values are numeric and generally increasing
        values = []
        for cell in first_row[start_idx:]:
            if self._is_numeric(cell):
                values.append(self._parse_numeric_value(cell))
            else:
                return False

        # RPM values should be increasing and typically > 100
        if len(values) < 3:
            return False

        # Check if mostly increasing and values look like RPM (> 100)
        increasing_count = sum(1 for i in range(len(values)-1) if values[i+1] > values[i])
        return increasing_count >= len(values) * 0.6 and max(values) > 100

    def _detect_load_header(self, rows_data: List[List[str]], has_rpm_header: bool) -> bool:
        """Detect if the first column contains load values."""
        if not rows_data:
            return False

        # Start from row 1 if we have RPM header, else row 0
        start_row = 1 if has_rpm_header else 0
        if len(rows_data) - start_row < 3:
            return False

        # Check if first column values are numeric
        values = []
        for row in rows_data[start_row:]:
            if row and self._is_numeric(row[0]):
                values.append(self._parse_numeric_value(row[0]))
            else:
                return False

        # Load values (TPS) are typically 0-100, often decreasing from top to bottom
        if len(values) < 3:
            return False

        # Check if values look like load percentages (0-120 range typical)
        return all(0 <= v <= 120 for v in values)

    def _is_numeric(self, value: str) -> bool:
        """Check if a string value is numeric."""
        if not value:
            return False
        try:
            # Remove common suffixes like % or units
            clean_val = value.rstrip('%').strip()
            float(clean_val)
            return True
        except ValueError:
            return False

    def _parse_numeric_value(self, value: str) -> float:
        """Parse a numeric value from string, handling % suffix."""
        clean_val = value.rstrip('%').strip()
        return float(clean_val)

    def _parse_numeric_row(self, row: List[str]) -> List[float]:
        """Parse a row of numeric values."""
        result = []
        for cell in row:
            if self._is_numeric(cell):
                result.append(self._parse_numeric_value(cell))
            else:
                result.append(0.0)  # Default for invalid values
        return result

    def _generate_default_rpm_axis(self, n_cols: int) -> List[float]:
        """Generate a default RPM axis if not provided in paste."""
        if n_cols <= 0:
            return []
        # Common RPM axis: 500 to 8000 in reasonable steps
        step = max(500, (8000 - 500) // max(1, n_cols - 1))
        return [500.0 + i * step for i in range(n_cols)]

    def _generate_default_load_axis(self, n_rows: int) -> List[float]:
        """Generate a default load axis if not provided in paste."""
        if n_rows <= 0:
            return []
        # Common load axis: 100 down to 0 in reasonable steps
        step = 100.0 / max(1, n_rows - 1) if n_rows > 1 else 100.0
        return [100.0 - i * step for i in range(n_rows)]

    # ========== Target AFR/Lambda Table Methods ==========

    def _load_target_map_dialog(self):
        """Show file dialog to load a target AFR/Lambda map."""
        # Use same directory as VE map load, then last VE map's directory, then default
        if self._last_load_dir and self._last_load_dir.exists():
            default_path = self._last_load_dir
        elif self._last_ve_map_path and self._last_ve_map_path.parent.exists():
            default_path = self._last_ve_map_path.parent
        else:
            default_path = self.ve_map_manager.get_default_map_path().parent

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Target AFR/Lambda Map",
            str(default_path),
            "CSV Files (*.csv);;All Files (*.*)"
        )

        if file_path:
            self._last_load_dir = Path(file_path).parent
            self._save_settings()
            self._load_target_map(Path(file_path))

    def _load_target_map(self, file_path: Path):
        """Load a target AFR/Lambda map from file."""
        try:
            # Use same loader as VE map
            target_map, rpm_axis, load_axis, _ = VEMapManager.load_map(file_path)

            self.target_afr_map = target_map
            self.target_rpm_axis = rpm_axis
            self.target_load_axis = load_axis

            # Update table display
            self._setup_target_table()
            self._update_target_display()

            self.target_cell_info_label.setText(f"Loaded: {file_path.name}")
            self.target_cell_info_label.setStyleSheet("color: #4ec9b0; padding: 4px;")
            self.copy_target_btn.setEnabled(True)

        except Exception as e:
            QMessageBox.critical(
                self,
                "Load Error",
                f"Failed to load target map:\n{e}"
            )

    def _paste_target_from_clipboard(self):
        """Paste target AFR/Lambda map from clipboard."""
        clipboard = QApplication.clipboard()
        text = clipboard.text()

        if not text.strip():
            QMessageBox.warning(self, "Empty Clipboard", "No data found in clipboard.")
            return

        try:
            # Parse clipboard text (reuse VE map parsing)
            lines = text.strip().split('\n')
            rows_data = []

            for line in lines:
                if '\t' in line:
                    cells = line.split('\t')
                else:
                    cells = line.split(',')
                cells = [c.strip() for c in cells]
                if cells:
                    rows_data.append(cells)

            if not rows_data:
                QMessageBox.warning(self, "Parse Error", "Could not parse clipboard data.")
                return

            # Detect headers
            has_rpm_header = self._detect_rpm_header(rows_data[0])
            has_load_header = self._detect_load_header(rows_data, has_rpm_header)

            # Extract axes and data
            if has_rpm_header and has_load_header:
                rpm_axis = self._parse_numeric_row(rows_data[0][1:])
                load_axis = []
                target_data = []
                for row in rows_data[1:]:
                    if row:
                        load_axis.append(self._parse_numeric_value(row[0]))
                        target_data.append(self._parse_numeric_row(row[1:]))
            elif has_rpm_header:
                rpm_axis = self._parse_numeric_row(rows_data[0])
                load_axis = self._generate_default_load_axis(len(rows_data) - 1)
                target_data = [self._parse_numeric_row(row) for row in rows_data[1:]]
            elif has_load_header:
                load_axis = []
                target_data = []
                for row in rows_data:
                    if row:
                        load_axis.append(self._parse_numeric_value(row[0]))
                        target_data.append(self._parse_numeric_row(row[1:]))
                rpm_axis = self._generate_default_rpm_axis(len(target_data[0]) if target_data else 0)
            else:
                rpm_axis = self._generate_default_rpm_axis(len(rows_data[0]) if rows_data else 0)
                load_axis = self._generate_default_load_axis(len(rows_data))
                target_data = [self._parse_numeric_row(row) for row in rows_data]

            if not target_data or not target_data[0]:
                QMessageBox.warning(self, "Parse Error", "No valid data found in clipboard.")
                return

            n_rows = len(target_data)
            n_cols = len(target_data[0])

            # Validate dimensions
            for i, row in enumerate(target_data):
                if len(row) != n_cols:
                    QMessageBox.warning(
                        self, "Parse Error",
                        f"Row {i+1} has {len(row)} columns, expected {n_cols}."
                    )
                    return

            if len(rpm_axis) != n_cols:
                rpm_axis = self._generate_default_rpm_axis(n_cols)
            if len(load_axis) != n_rows:
                load_axis = self._generate_default_load_axis(n_rows)

            # Store the target map
            self.target_afr_map = np.array(target_data, dtype=np.float64)
            self.target_rpm_axis = rpm_axis
            self.target_load_axis = load_axis

            # Update display
            self._setup_target_table()
            self._update_target_display()

            self.target_cell_info_label.setText(f"Pasted {n_rows}x{n_cols} target map")
            self.target_cell_info_label.setStyleSheet("color: #4ec9b0; padding: 4px;")
            self.copy_target_btn.setEnabled(True)

        except Exception as e:
            QMessageBox.critical(
                self, "Paste Error",
                f"Failed to parse clipboard data:\n{e}"
            )

    def _copy_target_to_clipboard(self):
        """Copy the target AFR/Lambda map to clipboard."""
        if self.target_afr_map is None:
            return

        # Get display mode
        display_mode = self.target_display_combo.currentText()
        stoich = 14.7 if "Gasoline" in display_mode else (9.765 if "E85" in display_mode else 1.0)

        # Build tab-separated values string
        lines = []
        rows, cols = self.target_afr_map.shape
        for row in range(rows):
            row_values = []
            for col in range(cols):
                value = self.target_afr_map[row, col]
                if display_mode != "Lambda":
                    value = value * stoich
                row_values.append(f"{value:.2f}")
            lines.append("\t".join(row_values))

        clipboard = QApplication.clipboard()
        clipboard.setText("\n".join(lines))

        self.target_cell_info_label.setText("Copied to clipboard")
        self.target_cell_info_label.setStyleSheet("color: #4ec9b0; padding: 4px;")

    def _setup_target_table(self):
        """Set up the target AFR/Lambda table structure."""
        if self.target_afr_map is None:
            return

        rows, cols = self.target_afr_map.shape

        self.target_table.setRowCount(rows)
        self.target_table.setColumnCount(cols)

        # Set column headers (RPM values)
        headers = [str(int(rpm)) for rpm in self.target_rpm_axis]
        self.target_table.setHorizontalHeaderLabels(headers)

        # Set row headers (Load values)
        row_headers = [f"{load:.0f}%" for load in self.target_load_axis]
        self.target_table.setVerticalHeaderLabels(row_headers)

        # Set columns to stretch
        header = self.target_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.sectionDoubleClicked.connect(self._edit_target_column_header)

        vert_header = self.target_table.verticalHeader()
        vert_header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        vert_header.sectionDoubleClicked.connect(self._edit_target_row_header)

    def _update_target_display(self, display_mode: str = None):
        """Update the target table display based on selected format."""
        if self.target_afr_map is None:
            return

        if display_mode is None:
            display_mode = self.target_display_combo.currentText()

        # Get stoichiometric ratio for conversion
        if "Gasoline" in display_mode:
            stoich = 14.7
        elif "E85" in display_mode:
            stoich = 9.765
        else:
            stoich = 1.0  # Lambda

        rows, cols = self.target_afr_map.shape

        self.target_table.blockSignals(True)

        for row in range(rows):
            for col in range(cols):
                # Target map is stored as Lambda internally
                lambda_val = self.target_afr_map[row, col]
                display_val = lambda_val * stoich if stoich > 1 else lambda_val

                text = f"{display_val:.2f}"
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)

                # Color based on rich/lean (lambda-based)
                color = self._get_target_color(lambda_val)
                item.setBackground(QBrush(color))

                # Set text color based on brightness
                brightness = (color.red() * 299 + color.green() * 587 + color.blue() * 114) / 1000
                text_color = QColor(255, 255, 255) if brightness < 128 else QColor(0, 0, 0)
                item.setForeground(QBrush(text_color))

                self.target_table.setItem(row, col, item)

        self.target_table.blockSignals(False)
        self.target_table.viewport().update()

    def _get_target_color(self, lambda_val: float) -> QColor:
        """Get color for target Lambda value."""
        if lambda_val < 0.80:
            return QColor(70, 70, 180)  # Very rich - blue
        elif lambda_val < 0.90:
            return QColor(80, 100, 160)  # Rich - blue-ish
        elif lambda_val < 0.98:
            return QColor(100, 130, 80)  # Slightly rich - green-ish
        elif lambda_val <= 1.02:
            return QColor(80, 150, 80)  # Stoich - green
        elif lambda_val < 1.10:
            return QColor(180, 150, 60)  # Slightly lean - yellow
        else:
            return QColor(180, 80, 80)  # Lean - red

    def _on_target_cell_clicked(self, row: int, col: int):
        """Handle target table cell click."""
        if self.target_afr_map is None:
            return

        rpm = self.target_rpm_axis[col]
        load = self.target_load_axis[row]
        lambda_val = self.target_afr_map[row, col]

        # Show in current display mode
        display_mode = self.target_display_combo.currentText()
        if "Gasoline" in display_mode:
            afr = lambda_val * 14.7
            info = f"RPM: {rpm:.0f} | Load: {load:.0f}% | Lambda: {lambda_val:.3f} | AFR: {afr:.1f}"
        elif "E85" in display_mode:
            afr = lambda_val * 9.765
            info = f"RPM: {rpm:.0f} | Load: {load:.0f}% | Lambda: {lambda_val:.3f} | AFR (E85): {afr:.1f}"
        else:
            info = f"RPM: {rpm:.0f} | Load: {load:.0f}% | Lambda: {lambda_val:.3f}"

        self.target_cell_info_label.setText(info)
        self.target_cell_info_label.setStyleSheet("color: #cccccc; padding: 4px;")

    def _edit_target_column_header(self, col: int):
        """Edit target table column header (RPM value)."""
        if not self.target_rpm_axis or col >= len(self.target_rpm_axis):
            return

        current_value = self.target_rpm_axis[col]

        value, ok = QInputDialog.getDouble(
            self,
            "Edit RPM Value",
            f"Enter new RPM value for column {col + 1}:",
            current_value,
            0, 20000, 0
        )

        if ok:
            self.target_rpm_axis[col] = value
            self.target_table.setHorizontalHeaderItem(
                col, QTableWidgetItem(str(int(value)))
            )

    def _edit_target_row_header(self, row: int):
        """Edit target table row header (Load value)."""
        if not self.target_load_axis or row >= len(self.target_load_axis):
            return

        current_value = self.target_load_axis[row]

        value, ok = QInputDialog.getDouble(
            self,
            "Edit Load Value",
            f"Enter new Load/TPS value for row {row + 1}:",
            current_value,
            0, 120, 1
        )

        if ok:
            self.target_load_axis[row] = value
            self.target_table.setVerticalHeaderItem(
                row, QTableWidgetItem(f"{value:.0f}%")
            )

    # ========== Engine Model Methods ==========

    def _load_engine_configs(self):
        """Load saved engine configurations into combo box."""
        self.engine_combo.blockSignals(True)
        self.engine_combo.clear()

        # Add "None" option
        self.engine_combo.addItem("-- Select Engine --")

        # Add saved configs
        config_names = EngineConfigManager.get_config_names()
        for name in config_names:
            self.engine_combo.addItem(name)

        # Try to load last used config from settings
        settings_file = self._get_settings_file()
        if settings_file.exists():
            try:
                with open(settings_file, 'r') as f:
                    settings = json.load(f)
                last_engine = settings.get('last_engine_config')
                if last_engine and last_engine in config_names:
                    self.engine_combo.setCurrentText(last_engine)
            except (json.JSONDecodeError, IOError):
                pass

        self.engine_combo.blockSignals(False)

        # Manually trigger selection if an engine was restored
        current = self.engine_combo.currentText()
        if current and current != "-- Select Engine --":
            self._on_engine_selected(current)

    def _on_engine_selected(self, name: str):
        """Handle engine selection change."""
        if name == "-- Select Engine --":
            self.engine_config = None
            self.ve_model = None
            self._update_model_ui()
            return

        configs = EngineConfigManager.load_configs()
        if name in configs:
            self.engine_config = configs[name]
            self.ve_model = AlphaNModel(self.engine_config)
            self._update_model_ui()

            # Save as last used
            self._save_last_engine(name)

    def _save_last_engine(self, name: str):
        """Save last used engine config name to settings."""
        settings_file = self._get_settings_file()
        try:
            settings = {}
            if settings_file.exists():
                with open(settings_file, 'r') as f:
                    settings = json.load(f)

            settings['last_engine_config'] = name

            with open(settings_file, 'w') as f:
                json.dump(settings, f, indent=2)
        except (json.JSONDecodeError, IOError):
            pass

    def _open_engine_config(self):
        """Open engine configuration dialog."""
        from mfviewer.gui.engine_config_dialog import EngineConfigDialog

        dialog = EngineConfigDialog(self.engine_config, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_config = dialog.get_config()
            if new_config:
                self.engine_config = new_config
                self.ve_model = AlphaNModel(self.engine_config)

                # Refresh combo and select new config
                self._load_engine_configs()
                self.engine_combo.setCurrentText(new_config.name)

                self._update_model_ui()

    def _update_model_ui(self):
        """Update model fitting UI state."""
        has_engine = self.engine_config is not None
        has_data = self.hit_count_map is not None and bool(np.sum(self.hit_count_map) > 0)

        self.fit_model_btn.setEnabled(bool(has_engine and has_data))

        has_model = self.ve_model is not None and self.ve_model.fit_stats is not None
        self.fill_cells_btn.setEnabled(bool(has_model))

        # Update fit statistics display
        if has_model and self.ve_model.fit_stats:
            stats = self.ve_model.fit_stats
            self.fit_r2_label.setText(f"R\u00b2: {stats.r_squared:.3f}")
            self.fit_rmse_label.setText(f"RMSE: {stats.rmse:.2f}%")

            # Color R² based on quality
            if stats.r_squared >= 0.90:
                r2_color = "#4ec9b0"  # Green
            elif stats.r_squared >= 0.75:
                r2_color = "#dcdcaa"  # Yellow
            else:
                r2_color = "#ce9178"  # Orange
            self.fit_r2_label.setStyleSheet(f"color: {r2_color};")
        else:
            self.fit_r2_label.setText("R\u00b2: -")
            self.fit_r2_label.setStyleSheet("color: #aaaaaa;")
            self.fit_rmse_label.setText("RMSE: -")

        # Update cell counts
        self._update_cell_counts()

    def _update_cell_counts(self):
        """Update measured/extrapolated cell count labels."""
        if self.hit_count_map is not None:
            min_samples = self.min_samples_spin.value()
            measured = int(np.sum(self.hit_count_map >= min_samples))
            self.measured_cells_label.setText(f"Measured: {measured}")
        else:
            self.measured_cells_label.setText("Measured: -")

        if self.extrapolated_mask is not None:
            extrapolated = int(np.sum(self.extrapolated_mask))
            self.extrapolated_cells_label.setText(f"Extrapolated: {extrapolated}")
        else:
            self.extrapolated_cells_label.setText("Extrapolated: -")

    def _fit_model(self):
        """Fit the VE model to measured data."""
        if self.ve_model is None or self.hit_count_map is None:
            return

        if self.corrected_ve_map is None:
            QMessageBox.warning(
                self, "No Data",
                "Calculate corrections first before fitting the model."
            )
            return

        min_samples = self.min_samples_spin.value()

        # Collect measured data points
        rpm_values = []
        tps_values = []
        ve_values = []
        weights = []

        rows, cols = self.hit_count_map.shape
        for row in range(rows):
            for col in range(cols):
                hit_count = self.hit_count_map[row, col]
                if hit_count >= min_samples:
                    # Get cell center values
                    rpm = self.rpm_axis[col]
                    tps = self.load_axis[row]
                    ve = self.corrected_ve_map[row, col]

                    rpm_values.append(rpm)
                    tps_values.append(tps)
                    ve_values.append(ve)
                    weights.append(hit_count)

        if len(rpm_values) < 5:
            QMessageBox.warning(
                self, "Insufficient Data",
                f"Need at least 5 cells with >= {min_samples} samples to fit model.\n"
                f"Found: {len(rpm_values)} cells."
            )
            return

        # Convert to numpy arrays
        rpm_arr = np.array(rpm_values, dtype=np.float64)
        tps_arr = np.array(tps_values, dtype=np.float64)
        ve_arr = np.array(ve_values, dtype=np.float64)
        weight_arr = np.array(weights, dtype=np.float64)

        # Fit the model
        stats = self.ve_model.fit(rpm_arr, tps_arr, ve_arr, weight_arr)

        # Update UI
        self._update_model_ui()

        # Show result
        if stats.r_squared > 0:
            QMessageBox.information(
                self, "Model Fitted",
                f"Model fitted successfully!\n\n"
                f"R\u00b2: {stats.r_squared:.3f}\n"
                f"RMSE: {stats.rmse:.2f}%\n"
                f"Max Error: {stats.max_error:.2f}%\n"
                f"Data Points: {stats.n_points}"
            )
        else:
            error_msg = "Model fitting failed or produced poor results.\n"
            if stats.error_message:
                error_msg += f"\nError: {stats.error_message}"
            else:
                error_msg += "Try adjusting engine parameters or getting more data."
            QMessageBox.warning(self, "Fit Failed", error_msg)

    def _fill_empty_cells(self):
        """Fill empty cells using the fitted model."""
        if self.ve_model is None or self.ve_model.fit_stats is None:
            QMessageBox.warning(
                self, "No Model",
                "Fit the model first before filling empty cells."
            )
            return

        if self.corrected_ve_map is None:
            return

        min_samples = self.min_samples_spin.value()
        rows, cols = self.corrected_ve_map.shape

        # Initialize extrapolated mask
        self.extrapolated_mask = np.zeros((rows, cols), dtype=bool)

        filled_count = 0

        for row in range(rows):
            for col in range(cols):
                # Skip cells with sufficient measured data
                if self.hit_count_map[row, col] >= min_samples:
                    continue

                # Get cell center values
                rpm = self.rpm_axis[col]
                tps = self.load_axis[row]

                # Predict VE using model
                predicted_ve = self.ve_model.predict(rpm, tps)

                # Apply to corrected map
                self.corrected_ve_map[row, col] = predicted_ve

                # Calculate implied correction
                if self.base_ve_map[row, col] > 0:
                    self.correction_map[row, col] = predicted_ve / self.base_ve_map[row, col]

                # Mark as extrapolated
                self.extrapolated_mask[row, col] = True
                filled_count += 1

        # Update display
        self._update_map_display()
        self._update_cell_counts()
        self.save_map_btn.setEnabled(True)
        self.copy_map_btn.setEnabled(True)

        QMessageBox.information(
            self, "Cells Filled",
            f"Filled {filled_count} empty cells using the engine model.\n"
            f"Extrapolated cells are shown with a blue tint."
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
            QTabWidget::pane {
                border: 1px solid #3e3e42;
                background-color: #1e1e1e;
            }
            QTabWidget::tab-bar {
                alignment: left;
            }
            QTabBar::tab {
                background-color: #2d2d2d;
                color: #cccccc;
                padding: 8px 16px;
                border: 1px solid #3e3e42;
                border-bottom: none;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #1e1e1e;
                color: #ffffff;
                border-bottom: 2px solid #007acc;
            }
            QTabBar::tab:hover:!selected {
                background-color: #383838;
            }
            QCheckBox {
                color: #dcdcdc;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border-radius: 2px;
                border: 2px solid #3e3e42;
                background-color: #252526;
            }
            QCheckBox::indicator:checked {
                background-color: #007acc;
                border-color: #007acc;
            }
            QCheckBox::indicator:hover {
                border-color: #007acc;
            }
            QInputDialog {
                background-color: #1e1e1e;
                color: #dcdcdc;
            }
        """)
