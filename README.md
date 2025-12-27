# MFViewer - Motorsports Fusion Telemetry Viewer

A Python-based desktop application for viewing and analyzing telemetry log files with advanced multi-log comparison capabilities.

## Features

### Performance Optimizations (v0.5.1)
- **Polars Backend**: Uses Polars for 10-100x faster CSV loading compared to pandas
- **Parquet Caching**: Automatically caches parsed files as Parquet for instant repeat loads
- **Background Loading**: File loading runs in a background thread with progress feedback - UI stays responsive
- **Float32 Storage**: Uses 32-bit floats for 50% memory reduction on large files
- **GPU Acceleration** (optional): CuPy support for faster array operations on NVIDIA GPUs
- **Graceful Fallbacks**: Automatically uses best available backend (cuDF → Polars → pandas)
- **UI Responsiveness Optimizations**:
  - Legend update debouncing at 30 FPS for smooth cursor interaction
  - Visible-tab-only refresh - hidden tabs refresh lazily when activated
  - Deferred auto-scale batches multiple channel additions
  - O(1) legend and color caching for instant lookups
  - Pre-computed channel statistics at parse time
  - Level of Detail (LOD) for faster initial plotting of large datasets
  - GPU-accelerated batch interpolation for legend values (5+ channels)

### Multi-Log Comparison
- **Load Multiple Logs**: Compare data from multiple runs simultaneously
- **Automatic Time Alignment**: All logs automatically align to start at time 0 for easy comparison
- **Time Synchronization**: Fine-tune time offsets between logs with dedicated dark-mode dialog
  - Auto-align all logs to zero
  - Align to main log
  - Manual offset adjustment with 0.001s precision
- **Visual Differentiation**:
  - Same color per channel across all logs for easy identification
  - Different line styles per log (solid, long dash, dots, dash-dot, dash-dot-dot)
  - Enhanced dash patterns for better visibility
- **Unified Legend**: Single legend entry per channel showing values from all logs side-by-side
  - Format: "RPM: 5432 | 5401 | -- rpm" (-- for missing data)
  - Cursor-based value display works correctly across all logs
- **Time Offset Applied to Data**: Time offsets modify the actual telemetry data
  - Consistent behavior when adding channels via drag/drop or double-click
  - Offsets properly preserved when replacing log files
- **Log Management**: Easy activation/deactivation of logs without reloading from disk
  - Right-click context menu for quick log management
  - Replace log file option to swap data while preserving settings
  - Refresh all logs from disk (F5)
  - Checkbox interface for instant log visibility toggle
  - All log data stored in memory for responsive switching

### Core Features
- **Haltech ECU Data Support**: Native support for Haltech ECU log files with automatic unit conversions
- **Data Parsing**: Parses CSV log files with metadata and channel information
- **Time-Series Plotting**: Interactive plots with zoom, pan, and multi-channel support using PyQtGraph
  - Synchronized X-axis across all plots (including horizontally tiled)
  - Auto-scale with outlier exclusion
  - Percentage channels automatically scale to 0-100%
- **Multi-Tab Interface**: Create multiple plot tabs to organize different channel groups
  - Tab close only via context menu (prevents accidental closure)
  - Horizontal and vertical plot tiling within tabs
- **Session Persistence**: Automatically saves and restores your last workspace on startup
  - Remembers last loaded tab configuration file
- **Save/Load Configurations**: Save/Save As workflow for tab layouts and channel selections
  - Y-axis scaling state preserved in configurations
  - Progress dialog shows loading status
  - Ctrl+S for quick save to current file
  - Ctrl+Shift+S for Save As
- **Channel Browser**: High-contrast dark mode tree view of all available channels grouped by type
- **Unit Conversions**: Intelligent unit conversion system with customizable multipliers
  - Automatic gauge pressure conversions for Fuel Pressure, Fuel - Load (MAP), Ignition - Load (MAP), and Manifold Pressure
  - Percentage channels correctly scaled (raw / 10)
  - Temperature, angle, current, voltage, and AFR conversions
  - Support for multiple AFR fuel types (gasoline, ethanol, methanol, diesel)
- **State Labels**: Human-readable state labels for channels like Idle Control State
  - Shows both numeric value and meaning (e.g., "3 (Closed Loop)")
- **Dark Theme**: Professional GitHub-inspired dark mode interface optimized for long viewing sessions
  - Dark title bars on Windows 11
  - Dark mode tooltips, dialogs, and progress indicators
  - High-contrast channel tree with bright indicators
  - Customized scrollbars, checkboxes, and UI elements
  - Attractive dark mode styling throughout
- **Auto-Refresh**: Automatically refreshes all plots when loading new log files
- **Statistics**: Real-time legend display with current values for all plotted channels
- **Progress Feedback**: Dark mode progress dialogs with real-time step updates
- **Splash Screen**: Clean startup experience with branded splash screen and version display
- **Branded UI**: MF logo displayed in tab bar for professional appearance
- **Flexible Layout**: Fixed-width channel panel that doesn't resize with window, but can be manually adjusted
- **Cross-platform**: Works on Windows, macOS, and Linux

## Installation

### For End Users (Windows)

1. Download the latest installer: `MFViewer-Setup-0.5.1.exe`
2. Run the installer and follow the prompts
3. Launch MFViewer from the Start Menu or Desktop shortcut

**Configuration files are stored in:** `%LOCALAPPDATA%\MFViewer\MFViewer`

### For Developers

#### Prerequisites

- Python 3.8 or higher
- pip (Python package manager)

#### Setup

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

For building standalone executables and installers, see [BUILD.md](BUILD.md).

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

#### Multi-Log Comparison Workflow
1. **Load First Log**: File → Open (Ctrl+O) to load your first log file
2. **Load Additional Logs**: File → Open (Ctrl+O) again to add more log files for comparison
   - Each log appears in the log list panel with a checkbox
   - Logs are automatically aligned to start at time 0
3. **Plot Channels**: Double-click any channel to plot it from ALL active logs simultaneously
   - Main log (1st): Solid line
   - 2nd log: Dashed line
   - 3rd log: Dotted line
   - 4th log: Dash-dot line
   - 5th log: Dash-dot-dot line
4. **Manage Logs**:
   - **Checkbox**: Toggle log visibility on/off
   - **Right-click**: Context menu for activate/deactivate/remove/time sync
   - **× button**: Remove log from comparison
5. **Adjust Time Sync**: Tools → Time Synchronization (Ctrl+Shift+T)
   - Auto-align all to zero
   - Align to main log
   - Manual offset adjustments

#### Basic Usage
1. **Browse Channels**: Use the channel tree to see all available channels grouped by type
2. **Create Tabs**: Click the "+" button or press Ctrl+T to create new plot tabs
3. **Plot Data**: Double-click on a channel to add it to the current tab's plot
4. **Navigate Plot**:
   - Left-click and drag to pan
   - Right-click and drag to zoom
   - Mouse wheel to zoom
5. **Manage Tabs**:
   - Right-click tab for context menu (rename, new, close)
   - Double-click tab name to rename (or press F2)
   - Click "×" to close tabs (or press Ctrl+W)
   - Organize different channel groups in separate tabs
6. **Save/Load Configurations**:
   - **Ctrl+S**: Save to current file (or Save As if new)
   - **Ctrl+Shift+S**: Save As to new file
   - **Ctrl+L**: Load configuration
7. **Unit Preferences**: Tools → Preferences to customize:
   - Preferred units for each channel type
   - Custom multipliers for unit conversions
   - AFR fuel type selection

### Keyboard Shortcuts

- **Ctrl+O**: Open log file
- **F5**: Refresh all log files from disk
- **Ctrl+S**: Save tab configuration
- **Ctrl+Shift+S**: Save tab configuration as
- **Ctrl+L**: Load tab configuration
- **Ctrl+T**: New plot tab
- **Ctrl+W**: Close current tab
- **Ctrl+Shift+T**: Time synchronization dialog
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

### Core
- **PyQt6**: GUI framework
- **pandas**: Data processing fallback
- **numpy**: Numerical computations
- **pyqtgraph**: Fast, interactive plotting
- **openpyxl**: Excel export support
- **PyYAML**: Configuration management
- **platformdirs**: Cross-platform config directories

### Performance (automatically used when available)
- **polars**: High-performance DataFrame library (10-100x faster CSV loading)
- **pyarrow**: Parquet file support for caching

### GPU Acceleration (optional)
- **cupy-cuda12x**: GPU-accelerated array operations (requires NVIDIA GPU with CUDA 12.x)

## Development Roadmap

### Phase 1: Foundation ✓
- [x] CSV parser
- [x] Basic GUI shell
- [x] Time-series plotting

### Phase 2: Enhanced Visualization ✓
- [x] Multiple plot layouts (horizontal/vertical tiling)
- [x] Plot synchronization and linking
- [ ] Custom dashboard with gauges

### Phase 3: Data Analysis
- [ ] Export functionality (CSV, Excel, JSON)
- [ ] Advanced statistics
- [ ] Data filtering and resampling

### Phase 4: Performance ✓
- [x] Polars/cuDF high-performance data loading
- [x] Parquet caching for instant repeat loads
- [x] Background threading for responsive UI
- [x] GPU acceleration support (CuPy)
- [x] Float32 memory optimization

### Phase 5: Polish ✓
- [x] Keyboard shortcuts
- [x] Dark theme
- [x] User preferences
- [x] Multi-log comparison

## Contributing

Contributions are welcome! Feel free to open issues or submit pull requests.

## License

This project is provided as-is for educational and personal use.

## Acknowledgments

Built with Python and PyQt6 for the automotive telemetry community.
