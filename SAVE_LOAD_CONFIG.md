# Save and Load Tab Configurations

MFViewer now supports saving and loading your tab layouts, allowing you to quickly restore your preferred channel configurations.

## Features

### Save Configuration
Save your current tab layout with all channels to a file for later use.

**What is Saved:**
- Tab names
- Channels plotted in each tab
- Tab order

**What is NOT Saved:**
- Zoom/pan settings
- Window size/position
- The log file path (you'll need to open the log file separately)

### Load Configuration
Restore a previously saved tab configuration to quickly set up your workspace.

**Requirements:**
- A log file must be loaded first
- The configuration file must exist and be valid
- Channels referenced in the config must exist in the current log file

## How to Use

### Saving a Configuration

1. **Set up your tabs** with the channels you want:
   - Create multiple tabs (Ctrl+T)
   - Rename them descriptively (F2)
   - Add channels to each tab by double-clicking

2. **Save the configuration**:
   - Menu: **File → Save Tab Configuration** (Ctrl+S)
   - Choose a location and filename
   - Default: `~/.mfviewer/` directory
   - File extension: `.mfc` (MFViewer Config) or `.json`

3. **Confirm**: Status bar shows "Configuration saved to [filename]"

### Loading a Configuration

1. **Open a log file first**: File → Open (Ctrl+O)

2. **Load the configuration**:
   - Menu: **File → Load Tab Configuration** (Ctrl+L)
   - Select your saved `.mfc` or `.json` file
   - Click Open

3. **Result**:
   - All existing tabs are closed
   - New tabs are created with saved names
   - Channels are automatically plotted
   - First tab becomes active

### Warning Messages

**"No Data Loaded"**: You must open a log file before loading a configuration

**"Channel not found"**: Some channels in the config don't exist in the current log file (check console for details)

**"Load Failed"**: Invalid or corrupted configuration file

## File Format

Configuration files are JSON format, human-readable and editable.

### Example Configuration

```json
{
  "version": "1.0",
  "tabs": [
    {
      "name": "Engine",
      "channels": [
        "Engine RPM",
        "Throttle Position",
        "Manifold Pressure"
      ]
    },
    {
      "name": "Temperatures",
      "channels": [
        "Coolant Temperature",
        "Oil Temperature",
        "Intake Air Temperature"
      ]
    }
  ]
}
```

### File Structure

- **version**: Configuration format version (currently "1.0")
- **tabs**: Array of tab objects
  - **name**: Tab display name
  - **channels**: Array of channel name strings

## Use Cases

### 1. Standard Analysis Setup
Save your go-to tab layout for routine analysis:

```
my_standard_layout.mfc
- Tab 1: "Overview" - RPM, Speed, Throttle
- Tab 2: "Power" - Boost, Timing, AFR
- Tab 3: "Diagnostics" - Temps, Pressures, Voltages
```

### 2. Vehicle-Specific Configs
Different configurations for different vehicles:

```
racecar_config.mfc
street_car_config.mfc
dyno_testing_config.mfc
```

### 3. Team Sharing
Share configurations with team members:
- Engineer creates optimal layout
- Saves as `team_standard.mfc`
- Other team members load it for consistency

### 4. Issue Investigation
Save specific diagnostic layouts:

```
fuel_system_debug.mfc
ignition_analysis.mfc
sensor_validation.mfc
```

## Keyboard Shortcuts

| Action | Shortcut |
|--------|----------|
| Save Configuration | `Ctrl+S` |
| Load Configuration | `Ctrl+L` |
| Open Log File | `Ctrl+O` |

## Tips and Best Practices

1. **Use Descriptive Names**: Save configs with meaningful names like `race_analysis.mfc` not `config1.mfc`

2. **Test Before Saving**: Make sure your layout is exactly how you want it

3. **Organize by Purpose**: Create different configs for different analysis tasks

4. **Version Control**: Keep configs in version control if working in a team

5. **Backup Important Configs**: Save copies of critical configurations

6. **Check Channel Names**: If loading fails, check that channel names match between files

## Default Location

Configurations are saved to:
- **Windows**: `C:\Users\<username>\.mfviewer\`
- **macOS**: `/Users/<username>/.mfviewer/`
- **Linux**: `/home/<username>/.mfviewer/`

You can save to any location, but the default makes configs easy to find.

## Troubleshooting

### Configuration Won't Load
- **Cause**: Incompatible log file
- **Solution**: Ensure the log file has all channels referenced in the config

### Channels Missing After Load
- **Cause**: Channel names changed or don't exist in current log
- **Solution**: Check console output for warnings about missing channels

### File Not Found
- **Cause**: Configuration file moved or deleted
- **Solution**: Browse to correct location or recreate the configuration

## Future Enhancements

Potential future features:
- [ ] Auto-save last configuration
- [ ] Configuration templates library
- [ ] Export/import with data
- [ ] Cloud sync for configurations
- [ ] Config merge (combine multiple configs)

## Technical Details

### File Extension
`.mfc` = MFViewer Config (JSON format with custom extension for clarity)

### Compatibility
- Forward compatible: Old configs will work with new versions
- Version check: Unsupported versions show error message
- Validation: Invalid configs rejected with error message

### Performance
- Instant save (< 100ms for typical configs)
- Fast load (< 1s for dozens of channels)
- No file size limits (practical limit ~1000 channels)
