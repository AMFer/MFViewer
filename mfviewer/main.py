"""
Main entry point for MFViewer application.
"""

import sys
import argparse
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QSplashScreen
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap

from mfviewer.gui.mainwindow import MainWindow


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
        version='MFViewer 0.1.0'
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

    # Show splash screen
    splash_path = Path(__file__).parent.parent / 'Assets' / 'MFSplash.png'
    splash = None
    if splash_path.exists():
        pixmap = QPixmap(str(splash_path))
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
