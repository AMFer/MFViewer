# Session Persistence

MFViewer automatically saves your workspace and restores it when you restart the application.

## What is Saved

When you close MFViewer, it automatically saves:
- **Last opened log file** path
- **All tabs** with their names
- **Channels** plotted in each tab
- **Tab order**

## What is NOT Saved

- Zoom/pan settings on plots
- Window size and position
- Application preferences (those are separate)

## How It Works

### Automatic Save (On Exit)
- Triggered when you close the application
- No user action required
- Silent operation (no confirmation dialog)
- Saved to: `~/.mfviewer/last_session.json`

### Automatic Restore (On Startup)
- Happens when you launch MFViewer
- Only restores if:
  - Session file exists
  - Last log file still exists at saved path
  - File is valid and readable
- Silent operation (no confirmation dialog)

## User Experience

### First Launch
1. Start MFViewer
2. No previous session → Opens with one empty tab
3. Open a log file and add channels
4. Close MFViewer → Session is saved

### Subsequent Launches
1. Start MFViewer
2. Previous session exists → Automatically restores:
   - Opens last log file
   - Creates all tabs with saved names
   - Plots all channels in each tab
3. Ready to continue where you left off!

### File Moved/Deleted
If the log file has been moved or deleted:
- Session restore is skipped
- MFViewer opens with default empty state
- No error message (silent fail)
- You can manually open a different file

## Session File Location

**Default Location:**
- Windows: `C:\Users\<username>\.mfviewer\last_session.json`
- macOS: `/Users/<username>/.mfviewer/last_session.json`
- Linux: `/home/<username>/.mfviewer/last_session.json`

## File Format

The session file is JSON format:

```json
{
  "version": "1.0",
  "last_log_file": "C:/path/to/your/log.csv",
  "tabs": [
    {
      "name": "Engine",
      "channels": ["Engine RPM", "Throttle Position"]
    },
    {
      "name": "Temperatures",
      "channels": ["Coolant Temperature", "Oil Temperature"]
    }
  ]
}
```

## Use Cases

### 1. Daily Work Session
- Morning: Open MFViewer → Your analysis from yesterday is ready
- Evening: Close MFViewer → Everything saved automatically
- No manual save/load steps needed

### 2. Long-term Analysis
- Working on a specific log file for days/weeks
- MFViewer always opens to that exact setup
- Continue analysis seamlessly

### 3. Standard Workspace
- Configure your preferred tabs once
- MFViewer remembers it forever
- Consistent workspace every time

### 4. Quick Resume
- Had to restart computer
- Need to check something quickly
- MFViewer opens right where you were

## Managing Sessions

### Clear Session
To start fresh without a previous session:
1. Close MFViewer
2. Delete `~/.mfviewer/last_session.json`
3. Next launch will start clean

### Backup Session
To save your current session permanently:
1. Open `~/.mfviewer/last_session.json`
2. Copy to another location
3. Rename (e.g., `my_analysis_session.json`)
4. Use File → Load Tab Configuration to restore it later

### Multiple Sessions
Session persistence only saves the **last** workspace:
- Want multiple workspaces? Use saved configurations instead
- File → Save Tab Configuration for each workspace
- File → Load Tab Configuration to switch between them

## Difference from Saved Configurations

| Feature | Session Persistence | Saved Configuration |
|---------|-------------------|---------------------|
| Trigger | Automatic on exit | Manual save |
| File Path | Auto (hidden) | User chooses |
| Log File | Included | NOT included |
| Purpose | Resume last work | Reusable templates |
| Count | One (latest) | Unlimited |

**Session Persistence** = "Continue where I left off"
**Saved Configuration** = "Reusable workspace template"

## Privacy & Security

### File Paths Stored
The session file contains the **full path** to your last log file:
- Visible in plain text JSON
- Stored in your home directory
- Only accessible to your user account

### No Data Stored
Session files do NOT contain:
- Actual telemetry data
- Channel values
- Plot images
- Sensitive information

### Safe to Share
Session files are safe to share if:
- You remove or modify the `last_log_file` path
- File paths don't reveal sensitive directory structures

## Troubleshooting

### Session Not Restoring
**Symptoms:** MFViewer starts empty every time

**Possible Causes:**
1. Session file doesn't exist
2. Log file moved/deleted
3. Session file corrupted

**Solutions:**
1. Check if `~/.mfviewer/last_session.json` exists
2. Verify log file path in session file
3. Delete session file and create new session

### Wrong File Opens
**Symptoms:** MFViewer opens a different file than expected

**Cause:** You opened a different file last time

**Solution:** This is expected behavior - session saves the **last** file

### Channels Missing
**Symptoms:** Tabs restore but channels don't plot

**Possible Causes:**
1. Log file format changed
2. Channel names don't match
3. Current log file missing those channels

**Solutions:**
1. Check console for warnings
2. Manually add channels
3. Open the original log file

## Advanced Usage

### Disable Session Persistence
Currently not configurable. To disable:
1. Make session file read-only (prevents saving)
2. Or delete it before each launch

### Custom Session Location
Session location is hardcoded to `~/.mfviewer/`
Future versions may support custom locations

### Session Migration
Moving to a new computer:
1. Copy `~/.mfviewer/last_session.json`
2. Update `last_log_file` path in JSON
3. Place in `~/.mfviewer/` on new computer

## Benefits

1. **Zero Effort**: No manual save/load required
2. **Seamless Workflow**: Pick up exactly where you left off
3. **Time Saving**: No need to recreate workspace each time
4. **Consistency**: Same workspace every session
5. **Reliability**: Automatic - can't forget to save

## Future Enhancements

Potential improvements:
- [ ] Option to disable session persistence
- [ ] Multiple session slots
- [ ] Session history (undo session changes)
- [ ] Auto-save during work (crash recovery)
- [ ] Sync sessions across computers
