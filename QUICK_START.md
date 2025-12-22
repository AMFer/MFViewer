# MFViewer Quick Start Guide

Get started with MFViewer in minutes!

## Installation

```bash
# 1. Create virtual environment
python -m venv venv

# 2. Activate it (Windows)
venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the application
python run.py
```

## Opening Your First Log File

1. Click **File → Open** (or press `Ctrl+O`)
2. Navigate to your telemetry log file (.csv)
3. Click **Open**

The channel tree will populate with all available channels grouped by type.

## Creating Your First Plot

1. Expand a channel group in the left tree (e.g., "Angle", "Temperature")
2. **Double-click** any channel name
3. The channel will appear in the plot area
4. Repeat to add more channels

## Working with Multiple Tabs

### Create a New Tab
- Click the **"+"** button in the top-right corner, OR
- Press `Ctrl+T`, OR
- Menu: **View → New Plot Tab**

### Organize Channels
Each tab can show different channels. Example setup:

**Tab 1: "Engine"**
- Engine RPM
- Throttle Position
- Manifold Pressure

**Tab 2: "Temperatures"**
- Coolant Temperature
- Oil Temperature
- Intake Air Temperature

**Tab 3: "Fuel System"**
- Fuel Pressure
- Injector Duty Cycle
- Air/Fuel Ratio

### Rename Tabs
- **Double-click** on the tab name, OR
- Press `F2`
- Enter new name and press Enter

### Close Tabs
- Click the **"×"** on the tab, OR
- Press `Ctrl+W`
- Note: You can't close the last tab

## Navigating Plots

### Zoom
- **Right-click and drag** on the plot
- **Mouse wheel** up/down

### Pan
- **Left-click and drag** on the plot

### Reset View
- Right-click → "View All"
- Or use the auto-range button

## Managing Plot Channels

### Remove a Channel
1. Find the channel in the "Active Plots" list (right side)
2. Click to select it
3. Click **"Remove Selected"** button

### Clear All Channels
- Click **"Clear All"** button
- This clears only the current tab

## Tips & Tricks

1. **Organize by System**: Create tabs for different vehicle systems
2. **Use Descriptive Names**: "Engine Temps" is better than "Plot 2"
3. **Color Coding**: The app automatically assigns different colors to each channel
4. **Keyboard Shortcuts**: Learn Ctrl+T, Ctrl+W, F2 for faster workflow
5. **Multiple Windows**: You can open multiple log files in separate windows

## Common Workflows

### Comparing Two Runs
1. Open first log file
2. Create tabs for key metrics
3. Close the file
4. Open second log file
5. Create similar tabs
6. Compare visually

### Diagnosing Issues
1. **Tab 1 "Overview"**: Critical parameters (RPM, throttle, speed)
2. **Tab 2 "Sensors"**: All sensor inputs
3. **Tab 3 "Problem Area"**: Focus on specific failing system

### Performance Analysis
1. **Tab 1 "Power"**: RPM, throttle, boost, timing
2. **Tab 2 "Fuel"**: AFR, fuel pressure, injector duty
3. **Tab 3 "Drivetrain"**: Speed, gear, wheel slip

## Getting Help

- **About Dialog**: Help → About MFViewer
- **Documentation**: See README.md and MULTI_TAB_FEATURE.md
- **Source Code**: Check the mfviewer/ directory

## Next Steps

Once you're comfortable with the basics:
1. Experiment with different channel combinations
2. Create a standard tab layout for your vehicle
3. Learn all keyboard shortcuts for efficiency
4. Explore the statistics features (coming soon!)

Happy analyzing! 🏁
