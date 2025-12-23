"""
Main entry point for MFViewer application.
"""

import sys
import argparse
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QSplashScreen
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QPixmap, QPalette, QColor, QPainter, QFont

from mfviewer.gui.mainwindow import MainWindow

# Version number
VERSION = "0.3.0"


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='MFViewer - Motorsports Fusion Telemetry Viewer',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        'file',
        nargs='?',
        type=str,
        help='Path to telemetry log file to open'
    )

    parser.add_argument(
        '--version',
        action='version',
        version=f'MFViewer {VERSION}'
    )

    return parser.parse_args()


def main():
    """Main application entry point."""
    args = parse_args()

    # Enable high DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # Create application
    app = QApplication(sys.argv)
    app.setApplicationName("MFViewer")
    app.setOrganizationName("MFViewer")

    # Set dark mode palette for dialogs and title bars
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(45, 45, 48))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(220, 220, 220))
    palette.setColor(QPalette.ColorRole.Base, QColor(30, 30, 30))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(45, 45, 48))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(220, 220, 220))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(220, 220, 220))
    palette.setColor(QPalette.ColorRole.Text, QColor(220, 220, 220))
    palette.setColor(QPalette.ColorRole.Button, QColor(45, 45, 48))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(220, 220, 220))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))
    palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)

    # Show splash screen
    splash_path = Path(__file__).parent.parent / 'Assets' / 'MFSplash.png'
    splash = None
    if splash_path.exists():
        pixmap = QPixmap(str(splash_path))
        # Scale width to 50%, but height to 45%
        target_width = pixmap.width() // 2
        target_height = int(pixmap.height() * 0.45)
        pixmap = pixmap.scaled(
            target_width,
            target_height,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )

        # Draw version number on splash screen
        painter = QPainter(pixmap)
        painter.setPen(QColor(220, 220, 220))
        font = QFont("Arial", 10)
        painter.setFont(font)
        # Draw version in bottom right corner
        text_rect = QRect(0, pixmap.height() - 25, pixmap.width() - 10, 20)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom, f"v{VERSION}")
        painter.end()

        splash = QSplashScreen(pixmap, Qt.WindowType.WindowStaysOnTopHint)
        splash.show()
        app.processEvents()

    # Create main window
    window = MainWindow()
    window.show()

    # Close splash screen
    if splash:
        splash.finish(window)

    # Open file if provided
    if args.file:
        file_path = Path(args.file)
        if file_path.exists():
            window.open_file(str(file_path))
        else:
            print(f"Warning: File not found: {args.file}")

    # Run event loop
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
