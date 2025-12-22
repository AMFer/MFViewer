# MFViewer Features Summary

Complete overview of all features in MFViewer - MF ECU Telemetry Viewer.

## Core Features

### 1. MF Log File Parsing
**File:** `mfviewer/data/parser.py`

- Parses MF NSP CSV log files
- Extracts metadata (version, software, download time)
- Identifies 149+ channels with types and ranges
- Handles 130K+ samples efficiently
- Time-series indexing for fast queries
- Supports all MF data types (Raw, Angle, Temperature, etc.)

**Key Classes:**
- `ChannelInfo`: Channel metadata (name, ID, type, min/max)
- `MFLogParser`: Main parsing engine
- `TelemetryData`: Container with channel lookup and statistics

### 2. Interactive Time-Series Plotting
**File:** `mfviewer/gui/plot_widget.py`

- PyQtGraph-based high-performance plotting
- Multi-channel support (unlimited channels per tab)
- Interactive controls:
  - Pan: Left-click and drag
  - Zoom: Right-click and drag or mouse wheel
  - Auto-range to fit data
- 8 vibrant colors optimized for dark backgrounds
- Real-time legend with channel names
- Active plots list with remove functionality

**Plot Features:**
- Grid overlay with customizable opacity
- Axis labels with units
- NaN value filtering
- Memory-efficient data handling

### 3. Multi-Tab Workspace
**File:** `mfviewer/gui/mainwindow.py`

- Unlimited plot tabs
- Tab management:
  - Create: Ctrl+T or "+" button
  - Close: Ctrl+W or "×" button
  - Rename: F2 or double-click
- Independent channel lists per tab
- Drag to reorder tabs
- Last tab cannot be closed (always have one tab)

**Use Cases:**
- Organize by vehicle system (Engine, Fuel, Temps)
- Compare different metrics
- Separate diagnostic views
- Multiple analysis perspectives

### 4. Session Persistence
**File:** `mfviewer/utils/config.py`

**Automatic on Startup:**
- Restores last opened log file
- Recreates all tabs with names
- Plots all channels automatically
- Silent operation (no prompts)

**Automatic on Exit:**
- Saves current workspace state
- Stores to `~/.mfviewer/last_session.json`
- No user action required
- Handles file path validation

**Benefits:**
- Zero-effort workspace continuity
- Pick up exactly where you left off
- No manual save/load steps

### 5. Save/Load Configurations
**File:** `mfviewer/utils/config.py`, `mfviewer/gui/mainwindow.py`

**Save Configuration (Ctrl+S):**
- Exports tab layout to `.hvc` or `.json` file
- Stores tab names and channel lists
- User-chosen location and filename
- Reusable workspace templates

**Load Configuration (Ctrl+L):**
- Imports tab layout from file
- Requires log file to be open first
- Recreates tabs and plots channels
- Validates channel availability

**Use Cases:**
- Standard analysis setups
- Vehicle-specific configurations
- Team workspace sharing
- Issue investigation templates

### 6. Dark Theme
**File:** `mfviewer/gui/mainwindow.py`, `mfviewer/gui/plot_widget.py`

**Visual Design:**
- VS Code-inspired color palette
- Professional dark gray tones
- Bright blue accents (#007acc, #2a82da)
- High-contrast text (#dcdcdc on dark)

**Styled Components:**
- Main window and panels
- Menu bar and menus
- Toolbar with blue buttons
- Status bar (blue background)
- Channel tree (dark with hover)
- Tab widget with active indicator
- Plot area (very dark #1e1e1e)
- Buttons with hover effects
- List widgets
- Splitter handles

**Plot Theme:**
- Dark background (#1e1e1e)
- Light axes and labels (#dcdcdc)
- Subtle grid lines
- Dark legend background
- 8 vibrant plot colors

### 7. Channel Browser
**File:** `mfviewer/gui/mainwindow.py`

- Tree view grouped by channel type
- Expandable/collapsible groups
- Alphabetically sorted channels
- Double-click to add to plot
- Metadata stored in tree items
- Channel count: 149+ in example log

**Channel Types:**
- Raw (digital values)
- Angle (timing, position)
- Temperature
- Pressure
- Speed
- Voltage
- And more...

### 8. Statistics
**File:** `mfviewer/data/parser.py`

Per-channel statistics:
- Minimum value
- Maximum value
- Mean (average)
- Standard deviation
- Sample count
- Time range

**Access:**
- Programmatic via `TelemetryData.get_statistics()`
- Future: UI panel for visual stats

## User Interface

### Main Window Layout
```
┌─────────────────────────────────────────────┐
│  Menu Bar: File | View | Help               │
│  Toolbar: [Open] [New Tab]                  │
├──────────┬──────────────────────────────────┤
│          │  ┌────────────────┬──────┐      │
│ Channel  │  │ Plot 1 │ Plot 2│  [+] │      │
│ Tree     │  ├────────────────┴──────┤      │
│          │  │                        │      │
│ ◢ Raw    │  │   Plot Area            │      │
│   ▸ Ch1  │  │   (PyQtGraph)          │      │
│   ▸ Ch2  │  │                        │      │
│ ◢ Angle  │  │                        │      │
│   ▸ Ch3  │  │                        │      │
│          │  └────────────────────────┘      │
├──────────┴──────────────────────────────────┤
│  Status: Loaded 149 channels, 131K samples  │
└─────────────────────────────────────────────┘
```

### Keyboard Shortcuts

| Action | Shortcut |
|--------|----------|
| Open file | Ctrl+O |
| Save configuration | Ctrl+S |
| Load configuration | Ctrl+L |
| New tab | Ctrl+T |
| Close tab | Ctrl+W |
| Rename tab | F2 |
| Quit | Ctrl+Q |
| Zoom in | Ctrl++ |
| Zoom out | Ctrl+- |
| Reset zoom | Ctrl+0 |

## File Formats

### Input: MF CSV Logs
```
%DataLog%
DataLogVersion : 1.1
...
Channel : Engine RPM
ID : 12345
Type : Raw
DisplayMaxMin : 8000,0
...
11:27:25.000,value1,value2,...
```

### Output: Configuration Files (.hvc)
```json
{
  "version": "1.0",
  "tabs": [
    {
      "name": "Engine",
      "channels": ["RPM", "Throttle"]
    }
  ]
}
```

### Session File (last_session.json)
```json
{
  "version": "1.0",
  "last_log_file": "/path/to/log.csv",
  "tabs": [...]
}
```

## Technical Stack

### Dependencies
- **PyQt6**: GUI framework (cross-platform)
- **pandas**: Data processing and CSV parsing
- **NumPy**: Numerical operations
- **PyQtGraph**: Fast plotting library
- **openpyxl**: Excel export (future)
- **PyYAML**: Configuration management

### Architecture
```
mfviewer/
├── data/          # Data layer
│   └── parser.py  # MF CSV parser
├── gui/           # Presentation layer
│   ├── mainwindow.py     # Main application
│   ├── plot_widget.py    # Plotting component
│   └── (future widgets)
├── utils/         # Utilities
│   └── config.py  # Configuration management
└── main.py        # Application entry point
```

### Performance
- **Parse Speed**: < 2 seconds for 130K samples
- **Plot Speed**: Real-time for millions of points
- **Memory**: Efficient DataFrame storage
- **Startup**: < 1 second (< 3s with session restore)

## Platform Support

### Tested Platforms
- Windows 10/11 ✓
- macOS (should work, untested)
- Linux (should work, untested)

### Requirements
- Python 3.8+
- 4GB RAM minimum
- 1920x1080 display recommended

## Documentation

### Available Guides
1. **README.md** - Installation and quick start
2. **QUICK_START.md** - Step-by-step beginner guide
3. **MULTI_TAB_FEATURE.md** - Multi-tab system details
4. **SAVE_LOAD_CONFIG.md** - Configuration management
5. **SESSION_PERSISTENCE.md** - Auto-save/restore
6. **DARK_MODE.md** - Theme documentation
7. **FEATURES_SUMMARY.md** - This file

## Future Roadmap

### Phase 2: Enhanced Visualization
- [ ] Custom dashboard with gauges
- [ ] Circular RPM gauge
- [ ] Temperature bars
- [ ] Multiple plot layouts
- [ ] Plot synchronization

### Phase 3: Data Analysis
- [ ] Export to CSV/Excel/JSON
- [ ] Advanced statistics panel
- [ ] Data filtering
- [ ] Resampling/downsampling
- [ ] Peak detection
- [ ] Time-in-range analysis

### Phase 4: Polish
- [ ] Performance optimizations (LTTB algorithm)
- [ ] Progress bars for long operations
- [ ] Recent files list
- [ ] User preferences dialog
- [ ] Light theme option
- [ ] Plot templates

### Phase 5: Advanced Features
- [ ] Compare multiple log files
- [ ] Overlay plots from different runs
- [ ] Math channels (calculated channels)
- [ ] Trigger detection
- [ ] Lap timing integration
- [ ] Video synchronization

## Version History

### v0.1.0 (Current)
- Initial release
- MF CSV parsing
- Multi-tab interface
- Dark theme
- Session persistence
- Save/load configurations
- Interactive plotting

## Credits

Built with Python and PyQt6 for the automotive telemetry community.

**Key Technologies:**
- PyQt6 by Riverbank Computing
- PyQtGraph by Luke Campagnola
- pandas by PyData community
- NumPy by NumPy developers

## License

This project is provided as-is for educational and personal use.
