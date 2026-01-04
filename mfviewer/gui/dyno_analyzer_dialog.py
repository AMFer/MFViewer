"""
Dyno Pull Analyzer Dialog for analyzing WOT dyno pulls from telemetry data.

This dialog provides:
- Automatic WOT region detection
- Multi-pull comparison with checkboxes
- AFR/Lambda analysis with lean/rich warnings
- Knock detection and counting
- Oil and fuel pressure monitoring
- Ignition timing analysis
- Summary dashboard with pass/warn/fail indicators
- Detailed RPM-binned breakdown table with comparison columns
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QGroupBox, QFormLayout,
    QDialogButtonBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QWidget, QSpinBox,
    QDoubleSpinBox, QAbstractItemView, QFrame,
    QSizePolicy, QListWidget, QListWidgetItem, QCheckBox,
    QSplitter
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QBrush, QFont

from mfviewer.utils.units import UnitsManager
from mfviewer.utils.config import TabConfiguration
from mfviewer.data.dyno_analyzer import (
    DynoPullAnalyzer, DynoPullResult, CHANNEL_PATTERNS
)
from mfviewer.data.log_manager import LogFileManager


# Colors for different pulls in comparison
PULL_COLORS = [
    QColor(100, 180, 255),   # Blue
    QColor(255, 150, 100),   # Orange
    QColor(100, 255, 150),   # Green
    QColor(255, 100, 255),   # Magenta
    QColor(255, 255, 100),   # Yellow
]


class StatusCard(QFrame):
    """A card widget showing status with pass/warn/fail indicator."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.title = title
        self.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Plain)
        self.setMinimumWidth(140)
        self.setMaximumWidth(180)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        # Title
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-weight: bold; color: #dcdcdc;")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_label)

        # Status badge
        self.status_label = QLabel("--")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("""
            padding: 4px 12px;
            border-radius: 3px;
            font-weight: bold;
            background-color: #3c3c3c;
            color: #888888;
        """)
        layout.addWidget(self.status_label)

        # Value line 1
        self.value1_label = QLabel("")
        self.value1_label.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        self.value1_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.value1_label)

        # Value line 2
        self.value2_label = QLabel("")
        self.value2_label.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        self.value2_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.value2_label)

        self._apply_style()

    def _apply_style(self):
        self.setStyleSheet("""
            StatusCard {
                background-color: #2d2d2d;
                border: 1px solid #3e3e42;
                border-radius: 4px;
            }
        """)

    def set_status(self, status: str, value1: str = "", value2: str = ""):
        """Set the card status and values."""
        self.value1_label.setText(value1)
        self.value2_label.setText(value2)

        if status == 'pass':
            self.status_label.setText("PASS")
            self.status_label.setStyleSheet("""
                padding: 4px 12px;
                border-radius: 3px;
                font-weight: bold;
                background-color: #2e7d32;
                color: #ffffff;
            """)
        elif status == 'warn':
            self.status_label.setText("WARN")
            self.status_label.setStyleSheet("""
                padding: 4px 12px;
                border-radius: 3px;
                font-weight: bold;
                background-color: #f57c00;
                color: #000000;
            """)
        elif status == 'fail':
            self.status_label.setText("FAIL")
            self.status_label.setStyleSheet("""
                padding: 4px 12px;
                border-radius: 3px;
                font-weight: bold;
                background-color: #c62828;
                color: #ffffff;
            """)
        else:
            self.status_label.setText("--")
            self.status_label.setStyleSheet("""
                padding: 4px 12px;
                border-radius: 3px;
                font-weight: bold;
                background-color: #3c3c3c;
                color: #888888;
            """)

    def set_no_data(self, message: str = "No data"):
        """Set card to no-data state."""
        self.status_label.setText("N/A")
        self.status_label.setStyleSheet("""
            padding: 4px 12px;
            border-radius: 3px;
            font-weight: bold;
            background-color: #3c3c3c;
            color: #666666;
        """)
        self.value1_label.setText(message)
        self.value2_label.setText("")


class PullListItem(QWidget):
    """Widget for a pull item in the list with checkbox and info."""

    def __init__(self, pull_index: int, start_time: float, end_time: float,
                 rpm_range: Tuple[float, float], color: QColor, parent=None):
        super().__init__(parent)
        self.pull_index = pull_index
        self.start_time = start_time
        self.end_time = end_time

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(8)

        # Checkbox
        self.checkbox = QCheckBox()
        self.checkbox.setChecked(pull_index == 0)  # First pull selected by default
        layout.addWidget(self.checkbox)

        # Color indicator
        color_label = QLabel()
        color_label.setFixedSize(12, 12)
        color_label.setStyleSheet(f"""
            background-color: rgb({color.red()}, {color.green()}, {color.blue()});
            border-radius: 2px;
        """)
        layout.addWidget(color_label)

        # Pull info
        duration = end_time - start_time
        rpm_min, rpm_max = rpm_range
        info_text = f"Pull {pull_index + 1}: {duration:.1f}s ({rpm_min:.0f}-{rpm_max:.0f} RPM)"
        info_label = QLabel(info_text)
        info_label.setStyleSheet("color: #dcdcdc;")
        layout.addWidget(info_label)

        layout.addStretch()

    def is_selected(self) -> bool:
        return self.checkbox.isChecked()


class DynoAnalyzerDialog(QDialog):
    """Dialog for analyzing WOT dyno pulls from telemetry data."""

    def __init__(self, log_manager: LogFileManager, units_manager: UnitsManager, parent=None):
        super().__init__(parent)
        self.log_manager = log_manager
        self.units_manager = units_manager
        self.analyzer: Optional[DynoPullAnalyzer] = None

        # Store detected pulls and their results
        self.detected_pulls: List[Tuple[float, float]] = []
        self.pull_results: Dict[int, DynoPullResult] = {}
        self.pull_items: List[PullListItem] = []

        # Discovered channels
        self.available_channels: List[str] = []
        self._discover_channels()

        self.setWindowTitle("Dyno Pull Analyzer")
        self.setMinimumWidth(1200)
        self.setMinimumHeight(750)
        self.resize(1400, 850)

        self._setup_ui()
        self._apply_dark_theme()
        self._load_settings()

        # Auto-detect channels after UI is set up
        QTimer.singleShot(100, self._auto_detect_channels)

    def _get_settings_file(self) -> Path:
        """Get the path to the dyno analyzer settings file."""
        return TabConfiguration.get_default_config_dir() / 'dyno_analyzer_settings.json'

    def _load_settings(self):
        """Load saved settings from config file."""
        settings_file = self._get_settings_file()
        if settings_file.exists():
            try:
                with open(settings_file, 'r') as f:
                    settings = json.load(f)
                self.tps_threshold_spin.setValue(settings.get('tps_threshold', 95))
                self.afr_target_spin.setValue(settings.get('afr_target', 12.5))
                self.oil_min_spin.setValue(settings.get('oil_min_psi', 25))
                self.rpm_bin_spin.setValue(settings.get('rpm_bin_size', 500))

                # Restore channel selections if they exist
                channel_map = settings.get('channel_map', {})
                for ch_type, combo in [
                    ('rpm', self.rpm_combo),
                    ('tps', self.tps_combo),
                    ('afr', self.afr_combo),
                    ('oil_pressure', self.oil_combo),
                    ('fuel_pressure', self.fuel_combo),
                    ('timing', self.timing_combo),
                    ('knock_count', self.knock_combo),
                ]:
                    saved_ch = channel_map.get(ch_type)
                    if saved_ch:
                        idx = combo.findText(saved_ch)
                        if idx >= 0:
                            combo.setCurrentIndex(idx)

            except (json.JSONDecodeError, IOError):
                pass  # Use defaults

    def _save_settings(self):
        """Save current settings to config file."""
        settings_file = self._get_settings_file()
        settings_file.parent.mkdir(parents=True, exist_ok=True)

        # Collect channel mappings
        channel_map = {
            'rpm': self.rpm_combo.currentText(),
            'tps': self.tps_combo.currentText(),
            'afr': self.afr_combo.currentText(),
            'oil_pressure': self.oil_combo.currentText(),
            'fuel_pressure': self.fuel_combo.currentText(),
            'timing': self.timing_combo.currentText(),
            'knock_count': self.knock_combo.currentText(),
        }

        settings = {
            'tps_threshold': self.tps_threshold_spin.value(),
            'afr_target': self.afr_target_spin.value(),
            'oil_min_psi': self.oil_min_spin.value(),
            'rpm_bin_size': self.rpm_bin_spin.value(),
            'channel_map': channel_map,
        }
        try:
            with open(settings_file, 'w') as f:
                json.dump(settings, f, indent=2)
        except IOError:
            pass

    def _discover_channels(self):
        """Discover available channels from loaded logs."""
        main_log = self.log_manager.get_main_log()
        if main_log and main_log.telemetry:
            self.available_channels = sorted(main_log.telemetry.get_channel_names())

    def _setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Main content - horizontal split
        content_layout = QHBoxLayout()
        content_layout.setSpacing(10)

        # Left side - Dashboard, pull list, and table (stretches)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        # Summary Dashboard
        dashboard_group = QGroupBox("Summary Dashboard")
        dashboard_layout = QHBoxLayout()
        dashboard_layout.setSpacing(10)

        self.afr_card = StatusCard("AFR/Lambda")
        dashboard_layout.addWidget(self.afr_card)

        self.knock_card = StatusCard("Knock")
        dashboard_layout.addWidget(self.knock_card)

        self.oil_card = StatusCard("Oil Pressure")
        dashboard_layout.addWidget(self.oil_card)

        self.fuel_card = StatusCard("Fuel Pressure")
        dashboard_layout.addWidget(self.fuel_card)

        self.timing_card = StatusCard("Timing")
        dashboard_layout.addWidget(self.timing_card)

        # Pull info panel
        info_frame = QFrame()
        info_frame.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Plain)
        info_frame.setStyleSheet("""
            QFrame {
                background-color: #2d2d2d;
                border: 1px solid #3e3e42;
                border-radius: 4px;
            }
        """)
        info_layout = QVBoxLayout(info_frame)
        info_layout.setContentsMargins(10, 8, 10, 8)
        info_layout.setSpacing(2)

        self.pull_count_label = QLabel("Pulls Found: --")
        self.pull_count_label.setStyleSheet("color: #aaaaaa; font-weight: bold;")
        info_layout.addWidget(self.pull_count_label)

        self.pull_duration_label = QLabel("Duration: --")
        self.pull_duration_label.setStyleSheet("color: #aaaaaa;")
        info_layout.addWidget(self.pull_duration_label)

        self.pull_rpm_label = QLabel("RPM Range: --")
        self.pull_rpm_label.setStyleSheet("color: #aaaaaa;")
        info_layout.addWidget(self.pull_rpm_label)

        dashboard_layout.addWidget(info_frame)
        dashboard_layout.addStretch()

        dashboard_group.setLayout(dashboard_layout)
        left_layout.addWidget(dashboard_group)

        # Pull Selection List
        pull_group = QGroupBox("Detected Pulls (check to compare)")
        pull_layout = QVBoxLayout()

        self.pull_list = QListWidget()
        self.pull_list.setMaximumHeight(120)
        self.pull_list.setStyleSheet("""
            QListWidget {
                background-color: #252526;
                border: 1px solid #3e3e42;
                border-radius: 3px;
            }
            QListWidget::item {
                padding: 2px;
            }
            QListWidget::item:selected {
                background-color: #094771;
            }
        """)
        pull_layout.addWidget(self.pull_list)

        # Update comparison button
        self.update_comparison_btn = QPushButton("Update Comparison")
        self.update_comparison_btn.clicked.connect(self._update_comparison)
        self.update_comparison_btn.setEnabled(False)
        pull_layout.addWidget(self.update_comparison_btn)

        pull_group.setLayout(pull_layout)
        left_layout.addWidget(pull_group)

        # RPM-Binned Detail Table with comparison columns
        table_group = QGroupBox("RPM-Binned Comparison")
        table_layout = QVBoxLayout()

        self.detail_table = QTableWidget()
        self.detail_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.detail_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.detail_table.setAlternatingRowColors(False)
        table_layout.addWidget(self.detail_table)

        # Status legend
        legend_layout = QHBoxLayout()
        legend_layout.setSpacing(15)

        for status, color, text in [
            ('pass', '#2e7d32', 'Pass'),
            ('warn', '#f57c00', 'Warning'),
            ('fail', '#c62828', 'Fail'),
        ]:
            indicator = QLabel(f"  {text}")
            indicator.setStyleSheet(f"""
                padding: 2px 8px;
                background-color: {color};
                border-radius: 2px;
                color: {'#000000' if status == 'warn' else '#ffffff'};
                font-size: 11px;
            """)
            legend_layout.addWidget(indicator)

        legend_layout.addStretch()
        table_layout.addLayout(legend_layout)

        table_group.setLayout(table_layout)
        left_layout.addWidget(table_group, 1)  # Stretch

        content_layout.addWidget(left_widget, 1)

        # Right side - Settings panel (fixed width)
        right_widget = QWidget()
        right_widget.setFixedWidth(220)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        # Detect Pulls button at top
        self.detect_btn = QPushButton("Detect Pulls")
        self.detect_btn.setStyleSheet("""
            QPushButton {
                background-color: #0e639c;
                color: #ffffff;
                border: none;
                padding: 10px 20px;
                border-radius: 3px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
            QPushButton:pressed {
                background-color: #007acc;
            }
        """)
        self.detect_btn.clicked.connect(self._detect_pulls)
        right_layout.addWidget(self.detect_btn)

        # Settings
        settings_group = QGroupBox("Settings")
        settings_layout = QFormLayout()
        settings_layout.setSpacing(6)

        self.tps_threshold_spin = QSpinBox()
        self.tps_threshold_spin.setRange(2, 100)
        self.tps_threshold_spin.setValue(95)
        self.tps_threshold_spin.setSuffix(" %")
        self.tps_threshold_spin.setToolTip("TPS threshold for WOT detection")
        self.tps_threshold_spin.valueChanged.connect(self._save_settings)
        settings_layout.addRow("TPS Thresh:", self.tps_threshold_spin)

        self.afr_target_spin = QDoubleSpinBox()
        self.afr_target_spin.setRange(10.0, 15.0)
        self.afr_target_spin.setValue(12.5)
        self.afr_target_spin.setSingleStep(0.1)
        self.afr_target_spin.setSuffix(":1")
        self.afr_target_spin.setToolTip("Target AFR for NA engines")
        self.afr_target_spin.valueChanged.connect(self._save_settings)
        settings_layout.addRow("AFR Target:", self.afr_target_spin)

        self.oil_min_spin = QSpinBox()
        self.oil_min_spin.setRange(10, 60)
        self.oil_min_spin.setValue(25)
        self.oil_min_spin.setSuffix(" psi")
        self.oil_min_spin.setToolTip("Minimum acceptable oil pressure")
        self.oil_min_spin.valueChanged.connect(self._save_settings)
        settings_layout.addRow("Min Oil PSI:", self.oil_min_spin)

        self.rpm_bin_spin = QSpinBox()
        self.rpm_bin_spin.setRange(250, 1000)
        self.rpm_bin_spin.setValue(500)
        self.rpm_bin_spin.setSingleStep(250)
        self.rpm_bin_spin.setSuffix(" RPM")
        self.rpm_bin_spin.setToolTip("RPM bin size for detail table")
        self.rpm_bin_spin.valueChanged.connect(self._save_settings)
        settings_layout.addRow("RPM Bin:", self.rpm_bin_spin)

        settings_group.setLayout(settings_layout)
        right_layout.addWidget(settings_group)

        # Channel Mapping
        channel_group = QGroupBox("Channel Mapping")
        channel_layout = QFormLayout()
        channel_layout.setSpacing(4)

        self.rpm_combo = QComboBox()
        self._populate_combo(self.rpm_combo, CHANNEL_PATTERNS.get('rpm', []))
        self.rpm_combo.currentTextChanged.connect(self._save_settings)
        channel_layout.addRow("RPM:", self.rpm_combo)

        self.tps_combo = QComboBox()
        self._populate_combo(self.tps_combo, CHANNEL_PATTERNS.get('tps', []))
        self.tps_combo.currentTextChanged.connect(self._save_settings)
        channel_layout.addRow("TPS:", self.tps_combo)

        self.afr_combo = QComboBox()
        self._populate_combo(self.afr_combo, CHANNEL_PATTERNS.get('afr', []))
        self.afr_combo.currentTextChanged.connect(self._save_settings)
        channel_layout.addRow("AFR:", self.afr_combo)

        self.oil_combo = QComboBox()
        self._populate_combo(self.oil_combo, CHANNEL_PATTERNS.get('oil_pressure', []))
        self.oil_combo.currentTextChanged.connect(self._save_settings)
        channel_layout.addRow("Oil PSI:", self.oil_combo)

        self.fuel_combo = QComboBox()
        self._populate_combo(self.fuel_combo, CHANNEL_PATTERNS.get('fuel_pressure', []))
        self.fuel_combo.currentTextChanged.connect(self._save_settings)
        channel_layout.addRow("Fuel PSI:", self.fuel_combo)

        self.timing_combo = QComboBox()
        self._populate_combo(self.timing_combo, CHANNEL_PATTERNS.get('timing', []))
        self.timing_combo.currentTextChanged.connect(self._save_settings)
        channel_layout.addRow("Timing:", self.timing_combo)

        self.knock_combo = QComboBox()
        self._populate_combo(self.knock_combo, CHANNEL_PATTERNS.get('knock_count', []))
        self.knock_combo.currentTextChanged.connect(self._save_settings)
        channel_layout.addRow("Knock:", self.knock_combo)

        channel_group.setLayout(channel_layout)
        right_layout.addWidget(channel_group)

        # Stretch at bottom
        right_layout.addStretch()

        content_layout.addWidget(right_widget, 0)

        layout.addLayout(content_layout)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # Set up detail table columns
        self._setup_detail_table()

    def _populate_combo(self, combo: QComboBox, preferred: List[str]):
        """Populate a combo box with available channels."""
        combo.clear()
        combo.addItem("")  # Empty option

        # Add preferred channels that exist
        added = set()
        for channel in preferred:
            if channel in self.available_channels:
                combo.addItem(channel)
                added.add(channel)

        # Separator if we found some
        if added:
            combo.insertSeparator(combo.count())

        # Add all other channels
        for channel in self.available_channels:
            if channel not in added:
                combo.addItem(channel)

    def _auto_detect_channels(self):
        """Auto-detect channels and select them in combos."""
        if not self.available_channels:
            return

        # Create temporary analyzer for detection
        main_log = self.log_manager.get_main_log()
        if not main_log or not main_log.telemetry:
            return

        temp_analyzer = DynoPullAnalyzer(main_log.telemetry, self.units_manager)
        detected = temp_analyzer.auto_detect_channels(self.available_channels)

        # Apply detected channels to combos
        for ch_type, combo in [
            ('rpm', self.rpm_combo),
            ('tps', self.tps_combo),
            ('afr', self.afr_combo),
            ('oil_pressure', self.oil_combo),
            ('fuel_pressure', self.fuel_combo),
            ('timing', self.timing_combo),
            ('knock_count', self.knock_combo),
        ]:
            channel = detected.get(ch_type)
            if channel:
                idx = combo.findText(channel)
                if idx >= 0:
                    combo.setCurrentIndex(idx)

    def _setup_detail_table(self):
        """Set up the detail table structure."""
        # Base headers - will add pull-specific columns dynamically
        headers = ["RPM"]
        self.detail_table.setColumnCount(len(headers))
        self.detail_table.setHorizontalHeaderLabels(headers)

        # Stretch columns
        header = self.detail_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    def _setup_analyzer(self) -> bool:
        """Set up the analyzer with current settings. Returns True if successful."""
        main_log = self.log_manager.get_main_log()
        if not main_log or not main_log.telemetry:
            QMessageBox.warning(
                self,
                "No Log Data",
                "Please load a telemetry log file first."
            )
            return False

        # Create analyzer
        self.analyzer = DynoPullAnalyzer(main_log.telemetry, self.units_manager)

        # Apply settings
        self.analyzer.update_settings(
            tps_threshold=self.tps_threshold_spin.value(),
            afr_target=self.afr_target_spin.value(),
            oil_min_psi=self.oil_min_spin.value(),
            rpm_bin_size=self.rpm_bin_spin.value(),
        )

        # Set channel mappings
        channel_combos = [
            ('rpm', self.rpm_combo),
            ('tps', self.tps_combo),
            ('afr', self.afr_combo),
            ('oil_pressure', self.oil_combo),
            ('fuel_pressure', self.fuel_combo),
            ('timing', self.timing_combo),
            ('knock_count', self.knock_combo),
        ]

        for ch_type, combo in channel_combos:
            channel = combo.currentText()
            if channel:
                self.analyzer.set_channel(ch_type, channel)

        # Check required channels
        if not self.analyzer.channel_map.get('rpm'):
            QMessageBox.warning(self, "Missing Channel", "Please select an RPM channel.")
            return False
        if not self.analyzer.channel_map.get('tps'):
            QMessageBox.warning(self, "Missing Channel", "Please select a TPS channel.")
            return False

        return True

    def _detect_pulls(self):
        """Detect all WOT pulls in the log."""
        if not self._setup_analyzer():
            return

        # Find WOT regions
        self.detected_pulls = self.analyzer.find_wot_regions()

        if not self.detected_pulls:
            QMessageBox.information(
                self,
                "No WOT Detected",
                f"No WOT regions found with TPS >= {self.tps_threshold_spin.value()}%.\n\n"
                "Try lowering the TPS threshold or check that the correct TPS channel is selected."
            )
            return

        # Clear previous results
        self.pull_results.clear()
        self.pull_items.clear()
        self.pull_list.clear()

        # Analyze each pull and populate the list
        for i, (start_time, end_time) in enumerate(self.detected_pulls):
            result = self.analyzer.analyze_pull(start_time, end_time)
            self.pull_results[i] = result

            # Get color for this pull
            color = PULL_COLORS[i % len(PULL_COLORS)]

            # Create list item
            item_widget = PullListItem(
                i, start_time, end_time,
                (result.rpm_min, result.rpm_max),
                color
            )
            item_widget.checkbox.stateChanged.connect(self._on_pull_selection_changed)
            self.pull_items.append(item_widget)

            list_item = QListWidgetItem()
            list_item.setSizeHint(item_widget.sizeHint())
            self.pull_list.addItem(list_item)
            self.pull_list.setItemWidget(list_item, item_widget)

        # Update pull count
        self.pull_count_label.setText(f"Pulls Found: {len(self.detected_pulls)}")

        # Enable comparison button
        self.update_comparison_btn.setEnabled(True)

        # Show first pull by default
        self._update_comparison()

    def _on_pull_selection_changed(self):
        """Handle pull selection checkbox changes."""
        # Update comparison button state
        selected_count = sum(1 for item in self.pull_items if item.is_selected())
        self.update_comparison_btn.setEnabled(selected_count > 0)

    def _update_comparison(self):
        """Update the comparison view with selected pulls."""
        selected_indices = [item.pull_index for item in self.pull_items if item.is_selected()]

        if not selected_indices:
            self.detail_table.setRowCount(0)
            return

        # Update dashboard with first selected pull
        first_result = self.pull_results.get(selected_indices[0])
        if first_result:
            self._update_dashboard(first_result)

        # Update comparison table
        self._update_comparison_table(selected_indices)

    def _update_dashboard(self, result: DynoPullResult):
        """Update the summary dashboard cards for a single pull."""
        # Pull info
        self.pull_duration_label.setText(f"Duration: {result.duration:.1f}s")
        self.pull_rpm_label.setText(f"RPM: {result.rpm_min:.0f} - {result.rpm_max:.0f}")

        # AFR card
        afr = result.afr
        if afr.message and "No" not in afr.message:
            self.afr_card.set_status(
                afr.status,
                f"Avg: {afr.average:.1f}:1",
                f"Range: {afr.minimum:.1f}-{afr.maximum:.1f}"
            )
        else:
            self.afr_card.set_no_data(afr.message or "No data")

        # Knock card
        knock = result.knock
        if knock.message and "No" not in knock.message[:10]:
            self.knock_card.set_status(
                knock.status,
                f"{knock.total_events} events",
                f"-{knock.max_retard:.1f}° retard" if knock.max_retard > 0 else ""
            )
        else:
            self.knock_card.set_no_data(knock.message or "No data")

        # Oil pressure card
        oil = result.oil_pressure
        if oil.message and "No" not in oil.message:
            self.oil_card.set_status(
                oil.status,
                f"Min: {oil.minimum:.0f} psi",
                f"Drop: {oil.drop_percent:.0f}%"
            )
        else:
            self.oil_card.set_no_data(oil.message or "No data")

        # Fuel pressure card
        fuel = result.fuel_pressure
        if fuel.message and "No" not in fuel.message:
            self.fuel_card.set_status(
                fuel.status,
                f"Min: {fuel.minimum:.0f} psi",
                f"Drop: {fuel.drop_percent:.0f}%"
            )
        else:
            self.fuel_card.set_no_data(fuel.message or "No data")

        # Timing card
        timing = result.timing
        if timing.message and "No" not in timing.message:
            self.timing_card.set_status(
                timing.status,
                f"Avg: {timing.average:.1f}°",
                f"{timing.retard_events} retards" if timing.retard_events > 0 else "Stable"
            )
        else:
            self.timing_card.set_no_data(timing.message or "No data")

    def _update_comparison_table(self, selected_indices: List[int]):
        """Update the RPM-binned comparison table."""
        if not selected_indices:
            self.detail_table.setRowCount(0)
            return

        # Collect all RPM bins from selected pulls
        all_rpms = set()
        for idx in selected_indices:
            result = self.pull_results.get(idx)
            if result and result.rpm_bin_data:
                for bin_data in result.rpm_bin_data:
                    all_rpms.add(bin_data.rpm)

        sorted_rpms = sorted(all_rpms)
        if not sorted_rpms:
            self.detail_table.setRowCount(0)
            return

        # Build headers: RPM + (AFR, Knock, Oil, Fuel, Timing) for each pull
        headers = ["RPM"]
        for idx in selected_indices:
            pull_num = idx + 1
            headers.extend([
                f"P{pull_num} AFR",
                f"P{pull_num} Knock",
                f"P{pull_num} Oil",
                f"P{pull_num} Fuel",
                f"P{pull_num} Timing",
            ])

        self.detail_table.setColumnCount(len(headers))
        self.detail_table.setHorizontalHeaderLabels(headers)
        self.detail_table.setRowCount(len(sorted_rpms))

        # Create lookup for each pull's data by RPM
        pull_data_by_rpm: Dict[int, Dict[float, any]] = {}
        for idx in selected_indices:
            result = self.pull_results.get(idx)
            if result and result.rpm_bin_data:
                pull_data_by_rpm[idx] = {
                    bin_data.rpm: bin_data for bin_data in result.rpm_bin_data
                }
            else:
                pull_data_by_rpm[idx] = {}

        # Fill table
        for row_idx, rpm in enumerate(sorted_rpms):
            # RPM column
            rpm_item = QTableWidgetItem(f"{rpm:.0f}")
            rpm_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.detail_table.setItem(row_idx, 0, rpm_item)

            # Data columns for each pull
            col_offset = 1
            for pull_idx in selected_indices:
                bin_data = pull_data_by_rpm[pull_idx].get(rpm)
                color = PULL_COLORS[pull_idx % len(PULL_COLORS)]

                # Determine row status
                row_status = 'pass'
                if bin_data:
                    row_status = bin_data.status

                # Get row tint color based on status
                if row_status == 'fail':
                    row_color = QColor(198, 40, 40, 40)
                elif row_status == 'warn':
                    row_color = QColor(245, 124, 0, 30)
                else:
                    row_color = None

                # AFR
                afr_text = f"{bin_data.afr:.1f}" if bin_data and bin_data.afr is not None else "--"
                afr_item = QTableWidgetItem(afr_text)
                afr_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                afr_item.setForeground(QBrush(color))
                if row_color:
                    afr_item.setBackground(QBrush(row_color))
                self.detail_table.setItem(row_idx, col_offset, afr_item)

                # Knock
                knock_text = str(bin_data.knock_count) if bin_data else "--"
                knock_item = QTableWidgetItem(knock_text)
                knock_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                knock_item.setForeground(QBrush(color))
                if row_color:
                    knock_item.setBackground(QBrush(row_color))
                self.detail_table.setItem(row_idx, col_offset + 1, knock_item)

                # Oil
                oil_text = f"{bin_data.oil_psi:.0f}" if bin_data and bin_data.oil_psi is not None else "--"
                oil_item = QTableWidgetItem(oil_text)
                oil_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                oil_item.setForeground(QBrush(color))
                if row_color:
                    oil_item.setBackground(QBrush(row_color))
                self.detail_table.setItem(row_idx, col_offset + 2, oil_item)

                # Fuel
                fuel_text = f"{bin_data.fuel_psi:.0f}" if bin_data and bin_data.fuel_psi is not None else "--"
                fuel_item = QTableWidgetItem(fuel_text)
                fuel_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                fuel_item.setForeground(QBrush(color))
                if row_color:
                    fuel_item.setBackground(QBrush(row_color))
                self.detail_table.setItem(row_idx, col_offset + 3, fuel_item)

                # Timing
                timing_text = f"{bin_data.timing_deg:.1f}°" if bin_data and bin_data.timing_deg is not None else "--"
                timing_item = QTableWidgetItem(timing_text)
                timing_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                timing_item.setForeground(QBrush(color))
                if row_color:
                    timing_item.setBackground(QBrush(row_color))
                self.detail_table.setItem(row_idx, col_offset + 4, timing_item)

                col_offset += 5

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
                gridline-color: #3e3e42;
                outline: none;
                selection-background-color: #094771;
                selection-color: #ffffff;
            }
            QTableWidget::item {
                padding: 4px;
                color: #dcdcdc;
            }
            QTableWidget QTableCornerButton::section {
                background-color: #333333;
                border: none;
                border-right: 1px solid #3e3e42;
                border-bottom: 1px solid #3e3e42;
            }
            QHeaderView::section {
                background-color: #333333;
                color: #dcdcdc;
                padding: 6px 8px;
                border: none;
                border-right: 1px solid #3e3e42;
                border-bottom: 1px solid #3e3e42;
                font-weight: bold;
            }
            QComboBox {
                background-color: #3c3c3c;
                color: #dcdcdc;
                border: 1px solid #3e3e42;
                padding: 4px 6px;
                border-radius: 2px;
                min-height: 18px;
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
                width: 18px;
                background-color: transparent;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 4px solid #dcdcdc;
                margin-right: 4px;
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
            QSpinBox, QDoubleSpinBox {
                background-color: #3c3c3c;
                color: #dcdcdc;
                border: 1px solid #3e3e42;
                padding: 4px 6px;
                border-radius: 2px;
            }
            QSpinBox:focus, QDoubleSpinBox:focus {
                border: 1px solid #007acc;
            }
            QSpinBox::up-button, QDoubleSpinBox::up-button,
            QSpinBox::down-button, QDoubleSpinBox::down-button {
                background-color: #4a4a4a;
                border: none;
                width: 16px;
            }
            QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
            QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
                background-color: #5a5a5a;
            }
            QDialogButtonBox {
                background-color: #1e1e1e;
            }
            QCheckBox {
                color: #dcdcdc;
                spacing: 6px;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border-radius: 2px;
                border: 1px solid #3e3e42;
                background-color: #252526;
            }
            QCheckBox::indicator:checked {
                background-color: #007acc;
                border-color: #007acc;
            }
            QCheckBox::indicator:hover {
                border-color: #007acc;
            }
        """)
