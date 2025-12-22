# Multi-Tab Plot Feature

MFViewer now supports multiple plot tabs, allowing you to organize different channel groups and views separately.

## Features

### Creating Tabs
- **"+" Button**: Click the "+" button in the top-right corner of the tab bar
- **Menu**: View → New Plot Tab
- **Keyboard**: `Ctrl+T`
- **Toolbar**: Click "New Tab" button

### Managing Tabs

#### Tab Context Menu (Right-Click)
Right-click on any tab to access quick actions:
- **Rename Tab**: Change the tab name
- **New Tab**: Create a new plot tab
- **Close Tab**: Close the selected tab (disabled if last tab)

#### Closing Tabs
- **Close Button**: Click the "×" on any tab (except the last one)
- **Right-Click**: Right-click → Close Tab
- **Menu**: View → Close Current Tab
- **Keyboard**: `Ctrl+W`
- **Protection**: Cannot close the last remaining tab

#### Renaming Tabs
- **Right-Click**: Right-click on a tab → Rename Tab
- **Double-Click**: Double-click on a tab name
- **Menu**: View → Rename Tab
- **Keyboard**: `F2`
- **Dialog**: Enter new name in the popup dialog

### Using Tabs

Each plot tab is independent and maintains its own:
- **Channel selection**: Different channels can be plotted on each tab
- **Plot configuration**: Zoom, pan, and view settings per tab
- **Legend**: Separate legend for each tab's channels

### Workflow Examples

#### Example 1: Engine vs Transmission
```
Tab 1: "Engine" - RPM, Throttle Position, Ignition Timing
Tab 2: "Transmission" - Gear Position, Clutch Switch, Vehicle Speed
Tab 3: "Fuel" - Fuel Pressure, Injector Duty, AFR
```

#### Example 2: Compare Runs
```
Tab 1: "Run 1" - All channels from first session
Tab 2: "Run 2" - Same channels from second session
Tab 3: "Comparison" - Key metrics side-by-side
```

#### Example 3: Diagnostics
```
Tab 1: "Overview" - Critical parameters
Tab 2: "Sensors" - All sensor inputs
Tab 3: "Outputs" - All actuator outputs
```

## Keyboard Shortcuts

| Action | Shortcut |
|--------|----------|
| New Tab | `Ctrl+T` |
| Close Tab | `Ctrl+W` |
| Rename Tab | `F2` |
| Next Tab | `Ctrl+Tab` |
| Previous Tab | `Ctrl+Shift+Tab` |

## UI Elements

### Tab Bar Features
- **Closable Tabs**: "×" button on each tab
- **"+" Button**: Always visible in corner for quick tab creation
- **Reorderable**: Drag tabs to reorder (standard Qt behavior)
- **Tab Names**: Clear, customizable names for organization

### Visual Design
- Dark theme tabs match overall UI
- Active tab highlighted with blue accent
- Hover effects for better usability
- Clean, minimal design

## Technical Details

### Implementation
- Each tab contains an independent `PlotWidget` instance
- Tabs are tracked in `self.plot_tabs` list
- Tab counter ensures unique default names
- Memory efficient: tabs are deleted when closed

### Channel Assignment
- Double-clicking a channel adds it to the **currently active tab**
- Switch tabs before adding channels to control placement
- Each tab maintains its own plot list and legend

## Tips

1. **Organize by System**: Create tabs for different vehicle systems
2. **Name Descriptively**: Use clear names like "Engine Temps" instead of "Plot 3"
3. **Use Multiple Windows**: Close tabs you're not using to reduce clutter
4. **Quick Access**: Use keyboard shortcuts for efficient tab management
5. **Save Your Work**: Tab configurations persist during the session

## Future Enhancements

Potential future features:
- [ ] Save/load tab configurations to file
- [ ] Export all tabs at once
- [ ] Tab templates for common setups
- [ ] Clone tab with all channels
- [ ] Tab groups/organization
