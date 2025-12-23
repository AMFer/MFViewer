"""
Log list widget for displaying and managing multiple log files.
"""

from typing import Optional
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QCheckBox, QLabel, QPushButton
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QPixmap, QPainter, QPen, QIcon

from mfviewer.data.log_manager import LogFile


# Line styles for visual indication
LOG_LINE_STYLES = [
    Qt.PenStyle.SolidLine,      # Main (1st)
    Qt.PenStyle.DashLine,       # 2nd
    Qt.PenStyle.DotLine,        # 3rd
    Qt.PenStyle.DashDotLine,    # 4th
    Qt.PenStyle.DashDotDotLine, # 5th
]


def create_line_style_icon(style: Qt.PenStyle, size: int = 20) -> QIcon:
    """
    Create an icon showing the line style.

    Args:
        style: Qt pen style
        size: Icon size in pixels

    Returns:
        QIcon with line style preview
    """
    pixmap = QPixmap(size * 2, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    pen = QPen(Qt.GlobalColor.white, 2, style)
    painter.setPen(pen)
    painter.drawLine(0, size // 2, size * 2, size // 2)
    painter.end()

    return QIcon(pixmap)


class LogListItem(QWidget):
    """Custom widget for a single log file item in the list."""

    item_toggled = pyqtSignal(int, bool)  # index, is_active
    item_removed = pyqtSignal(int)         # index

    def __init__(self, log_file: LogFile, active_index: int = 0):
        super().__init__()
        self.log_file = log_file
        self.active_index = active_index

        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2)
        layout.setSpacing(5)

        # Checkbox for active/inactive
        self.checkbox = QCheckBox()
        self.checkbox.setChecked(log_file.is_active)
        self.checkbox.toggled.connect(self._on_toggled)
        layout.addWidget(self.checkbox)

        # Line style icon
        self.style_label = QLabel()
        self._update_style_icon()
        layout.addWidget(self.style_label)

        # Filename label
        self.name_label = QLabel(log_file.display_name)
        self.name_label.setStyleSheet("color: #dcdcdc;")
        layout.addWidget(self.name_label, 1)  # Stretch

        # Close button
        close_button = QPushButton("×")
        close_button.setMaximumSize(QSize(20, 20))
        close_button.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #888;
                border: none;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                color: #ff6b6b;
                background-color: #3e3e42;
            }
        """)
        close_button.clicked.connect(self._on_remove_clicked)
        layout.addWidget(close_button)

        # Update background for main log
        self._update_background()

    def _update_style_icon(self):
        """Update the line style icon based on active index."""
        if self.checkbox.isChecked():
            style = LOG_LINE_STYLES[self.active_index % len(LOG_LINE_STYLES)]
            icon = create_line_style_icon(style)
            self.style_label.setPixmap(icon.pixmap(QSize(40, 20)))
        else:
            # Show empty for inactive logs
            self.style_label.clear()

    def _update_background(self):
        """Update background color (highlight main log)."""
        if self.active_index == 0 and self.checkbox.isChecked():
            # Main log - blue tint
            self.setStyleSheet("background-color: #2a4a6a;")
        else:
            # Normal background
            self.setStyleSheet("background-color: #2d2d30;")

    def update_active_index(self, active_index: int):
        """Update the active index and refresh visuals."""
        self.active_index = active_index
        self._update_style_icon()
        self._update_background()

    def _on_toggled(self, checked: bool):
        """Handle checkbox toggle."""
        self.item_toggled.emit(self.log_file.index, checked)

    def _on_remove_clicked(self):
        """Handle remove button click."""
        self.item_removed.emit(self.log_file.index)


class LogListWidget(QWidget):
    """Widget for displaying and managing multiple log files."""

    log_activated = pyqtSignal(int, bool)  # index, is_active
    log_removed = pyqtSignal(int)          # index

    def __init__(self):
        super().__init__()
        self._log_items = {}  # index -> (QListWidgetItem, LogListItem)

        self._setup_ui()

    def _setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # List widget
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet("""
            QListWidget {
                background-color: #252526;
                border: none;
                outline: none;
            }
            QListWidget::item {
                border: none;
                padding: 0px;
            }
            QListWidget::item:selected {
                background-color: #3e3e42;
            }
        """)
        layout.addWidget(self.list_widget)

    def add_log_file(self, log_file: LogFile):
        """
        Add a log file to the list.

        Args:
            log_file: Log file to add
        """
        # Calculate active index (position among active logs)
        active_index = self._get_active_index(log_file)

        # Create custom widget
        item_widget = LogListItem(log_file, active_index)
        item_widget.item_toggled.connect(self._on_item_toggled)
        item_widget.item_removed.connect(self._on_item_removed)

        # Create list item
        list_item = QListWidgetItem(self.list_widget)
        list_item.setSizeHint(item_widget.sizeHint())

        # Add to list
        self.list_widget.addItem(list_item)
        self.list_widget.setItemWidget(list_item, item_widget)

        # Store reference
        self._log_items[log_file.index] = (list_item, item_widget)

    def remove_log_file(self, index: int):
        """
        Remove a log file from the list.

        Args:
            index: Index of the log file to remove
        """
        if index in self._log_items:
            list_item, item_widget = self._log_items[index]
            row = self.list_widget.row(list_item)
            self.list_widget.takeItem(row)
            del self._log_items[index]

            # Update line styles for remaining items
            self.update_line_styles()

    def set_active(self, index: int, active: bool):
        """
        Set the active state of a log file.

        Args:
            index: Index of the log file
            active: New active state
        """
        if index in self._log_items:
            _, item_widget = self._log_items[index]
            item_widget.checkbox.setChecked(active)

    def update_line_styles(self):
        """Update line style icons for all items based on current active status."""
        # Build list of active indices in order
        active_items = []
        for idx in range(self.list_widget.count()):
            list_item = self.list_widget.item(idx)
            item_widget = self.list_widget.itemWidget(list_item)
            if item_widget and item_widget.checkbox.isChecked():
                active_items.append(item_widget)

        # Update active index for each active item
        for active_idx, item_widget in enumerate(active_items):
            item_widget.update_active_index(active_idx)

        # Update inactive items
        for idx in range(self.list_widget.count()):
            list_item = self.list_widget.item(idx)
            item_widget = self.list_widget.itemWidget(list_item)
            if item_widget and not item_widget.checkbox.isChecked():
                item_widget.update_active_index(0)  # Doesn't matter, won't show icon

    def _get_active_index(self, log_file: LogFile) -> int:
        """Get the active index for a log file (position among active logs)."""
        if not log_file.is_active:
            return 0

        active_count = 0
        for idx in range(self.list_widget.count()):
            list_item = self.list_widget.item(idx)
            item_widget = self.list_widget.itemWidget(list_item)
            if item_widget and item_widget.checkbox.isChecked():
                active_count += 1

        return active_count

    def _on_item_toggled(self, index: int, is_active: bool):
        """Handle item checkbox toggle."""
        self.log_activated.emit(index, is_active)

    def _on_item_removed(self, index: int):
        """Handle item remove button click."""
        self.log_removed.emit(index)
