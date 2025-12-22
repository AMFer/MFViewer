# MFViewer - Motorsports Fusion Telemetry Viewer

A Python-based desktop application for viewing and analyzing telemetry log files.

## Features

- **Data Parsing**: Parses CSV log files with metadata and channel information
- **Time-Series Plotting**: Interactive plots with zoom, pan, and multi-channel support using PyQtGraph
- **Multi-Tab Interface**: Create multiple plot tabs to organize different channel groups
- **Session Persistence**: Automatically saves and restores your last workspace on startup
- **Save/Load Configurations**: Save your tab layouts and channel selections for quick reuse
- **Channel Browser**: Tree view of all available channels grouped by type
- **Dark Theme**: Professional dark mode interface optimized for long viewing sessions
- **Statistics**: Basic statistics for telemetry channels
- **Cross-platform**: Works on Windows, macOS, and Linux

## Installation

### Prerequisites

- Python 3.8 or higher
- pip (Python package manager)

### Setup

1. Clone or download this repository

2. Create a virtual environment (recommended):
   ```bash
   python -m venv venv
   ```

3. Activate the virtual environment:
   - Windows:
     ```bash
     venv\Scripts\activate
     ```
   - macOS/Linux:
     ```bash
     source venv/bin/activate
     ```

4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

### Running the Application

Basic usage:
```bash
python run.py
```

Open a specific log file directly:
```bash
python run.py "path/to/logfile.csv"
```

Using the module:
```bash
python -m mfviewer.main
```

### Using the GUI

1. **Open a Log File**: Click File → Open or use Ctrl+O
2. **Browse Channels**: Use the left panel to see all available channels grouped by type
3. **Create Tabs**: Click the "+" button or press Ctrl+T to create new plot tabs
4. **Plot Data**: Double-click on a channel to add it to the current tab's plot
5. **Navigate Plot**:
   - Left-click and drag to pan
   - Right-click and drag to zoom
   - Mouse wheel to zoom
6. **Manage Tabs**:
   - Right-click tab for context menu (rename, new, close)
   - Double-click tab name to rename (or press F2)
   - Click "×" to close tabs (or press Ctrl+W)
   - Organize different channel groups in separate tabs
7. **Remove Plots**: Select a channel in the Active Plots list and click "Remove Selected"
8. **Clear All**: Click "Clear All" to remove all plots from the current tab

### Keyboard Shortcuts

- **Ctrl+O**: Open file
- **Ctrl+S**: Save tab configuration
- **Ctrl+L**: Load tab configuration
- **Ctrl+T**: New plot tab
- **Ctrl+W**: Close current tab
- **F2**: Rename current tab
- **Ctrl+Q**: Quit application

## Project Structure

```
MFViewer/
├── mfviewer/              # Main package
│   ├── data/            # Data parsing modules
│   │   └── parser.py    # CSV parser
│   ├── gui/             # GUI components
│   │   ├── mainwindow.py    # Main application window
│   │   └── plot_widget.py   # Plotting widget
│   ├── widgets/         # Custom widgets (future)
│   ├── utils/           # Utility modules
│   └── main.py          # Application entry point
├── tests/               # Test suite
├── requirements.txt     # Python dependencies
├── run.py              # Simple launcher script
└── README.md           # This file
```

## Dependencies

- **PyQt6**: GUI framework
- **pandas**: Data processing and manipulation
- **numpy**: Numerical computations
- **pyqtgraph**: Fast, interactive plotting
- **openpyxl**: Excel export support
- **PyYAML**: Configuration management

## Development Roadmap

### Phase 1: Foundation ✓
- [x] CSV parser
- [x] Basic GUI shell
- [x] Time-series plotting

### Phase 2: Enhanced Visualization
- [ ] Custom dashboard with gauges
- [ ] Multiple plot layouts
- [ ] Plot synchronization and linking

### Phase 3: Data Analysis
- [ ] Export functionality (CSV, Excel, JSON)
- [ ] Advanced statistics
- [ ] Data filtering and resampling

### Phase 4: Polish
- [ ] Performance optimizations
- [ ] Keyboard shortcuts
- [ ] Dark/light themes
- [ ] User preferences

## Contributing

Contributions are welcome! Feel free to open issues or submit pull requests.

## License

This project is provided as-is for educational and personal use.

## Acknowledgments

Built with Python and PyQt6 for the automotive telemetry community.
