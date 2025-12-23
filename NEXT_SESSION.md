# Next Session: Multi-Log File Comparison - Continue Implementation

## Current Status

We're implementing multi-log file comparison for MFViewer. Steps 1-3 are **COMPLETE**, and we need to continue with **Step 4** (the most critical step).

## What's Been Completed ✅

### Step 1: LogFileManager Data Model
**File:** `mfviewer/data/log_manager.py`

- Created `LogFile` dataclass and `LogFileManager` class
- All methods working: `add_log_file()`, `remove_log_file()`, `set_active()`, `get_main_log()`, `get_active_logs()`
- Tested and compiling successfully

### Step 2: LogListWidget UI Component
**File:** `mfviewer/widgets/log_list_widget.py`

- Custom widget with checkboxes, line style icons, filename labels, and close buttons
- Dark theme styling with blue tint for main log
- All signals connected: `log_activated`, `log_removed`
- Tested and compiling successfully

### Step 3: MainWindow Integration
**File:** `mfviewer/gui/mainwindow.py`

- ✅ Replaced `self.telemetry` with `self.log_manager`
- ✅ Added vertical splitter with log list above channel tree in `_setup_ui()`
- ✅ Updated `open_file()` to add logs instead of replacing
- ✅ Added event handlers: `_on_log_activated()`, `_on_log_removed()`
- ✅ Updated `_populate_channel_tree()` to use main log
- ✅ Updated `_on_channel_double_clicked()` to call `add_channel_from_all_logs()`
- ✅ Created `_refresh_all_plots()` that calls `refresh_with_multi_log()`
- ✅ Separated unit refresh into `_refresh_all_plots_with_new_units()`
- Tested and compiling successfully

## What Needs to Be Done Next ⏳

### **IMMEDIATE PRIORITY: Step 4 - Update Plotting with Line Styles**

⚠️ **The application WILL NOT RUN until we implement these methods in `mfviewer/gui/plot_widget.py`**

MainWindow is already calling these methods that don't exist yet:
- `plot_widget.add_channel_from_all_logs(channel_name, self.log_manager)`
- `plot_widget.refresh_with_multi_log(self.log_manager)`

### Required Changes to `mfviewer/gui/plot_widget.py`:

#### 1. Add Line Style Constants (at module level, after imports)

```python
from PyQt6.QtCore import Qt

# Line styles for multi-log comparison (up to 5 logs)
LOG_LINE_STYLES = [
    Qt.PenStyle.SolidLine,      # Main log (1st)
    Qt.PenStyle.DashLine,       # 2nd log
    Qt.PenStyle.DotLine,        # 3rd log
    Qt.PenStyle.DashDotLine,    # 4th log
    Qt.PenStyle.DashDotDotLine, # 5th log
]

def get_line_style_for_log(active_index: int) -> Qt.PenStyle:
    """Get line style for a log based on its position in active logs."""
    return LOG_LINE_STYLES[active_index % len(LOG_LINE_STYLES)]
```

#### 2. Update `plot_items` Structure in `PlotWidget.__init__()`

**Current:**
```python
self.plot_items: Dict[str, dict] = {}  # channel_name -> plot_info
```

**Change to:**
```python
self.plot_items: Dict[Tuple[str, int], dict] = {}  # (channel_name, log_index) -> plot_info
```

**Also update imports to include Tuple:**
```python
from typing import Optional, Dict, Tuple  # Add Tuple
```

#### 3. Modify `add_channel()` Method Signature and Implementation

**Current signature (around line 189):**
```python
def add_channel(self, channel: ChannelInfo, telemetry: TelemetryData):
```

**Change to:**
```python
def add_channel(self, channel: ChannelInfo, telemetry: TelemetryData,
                active_index: int = 0, log_file_path: Optional[Path] = None):
```

**Key changes inside add_channel():**

1. **Change plot_key:**
   ```python
   # OLD: Check if already plotted
   # if channel.name in self.plot_items:

   # NEW:
   plot_key = (channel.name, active_index)
   if plot_key in self.plot_items:
       return  # Already plotted
   ```

2. **Get line style:**
   ```python
   # After color selection, add:
   line_style = get_line_style_for_log(active_index)
   ```

3. **Create pen with style:**
   ```python
   # OLD: pen = pg.mkPen(color=color, width=2)
   # NEW:
   pen = pg.mkPen(color=color, width=2, style=line_style)
   ```

4. **Update legend name:**
   ```python
   # Add after pen creation:
   legend_name = channel.name
   if active_index > 0:
       legend_name = f"{channel.name} (Log {active_index + 1})"

   # Then use legend_name in plot call:
   plot_item = self.plot_widget.plot(time_data, values, pen=pen, name=legend_name)
   ```

5. **Store with new structure:**
   ```python
   # OLD: self.plot_items[channel.name] = {...}
   # NEW:
   self.plot_items[plot_key] = {
       'plot_item': plot_item,
       'channel': channel,
       'color': color,
       'log_index': active_index,  # NEW
       'log_file_path': log_file_path,  # NEW
       'line_style': line_style  # NEW
   }
   ```

#### 4. Add NEW Method: `add_channel_from_all_logs()`

Add this new method after `add_channel()`:

```python
def add_channel_from_all_logs(self, channel_name: str, log_manager):
    """
    Plot a channel from all active logs.

    Args:
        channel_name: Channel to plot
        log_manager: LogFileManager instance
    """
    active_logs = log_manager.get_active_logs()

    for active_index, log_file in enumerate(active_logs):
        channel = log_file.telemetry.get_channel(channel_name)

        if channel:
            self.add_channel(
                channel=channel,
                telemetry=log_file.telemetry,
                active_index=active_index,
                log_file_path=log_file.file_path
            )
        # Skip logs that don't have this channel
```

#### 5. Update `remove_channel()` Method

**Current signature (around line 324):**
```python
def remove_channel(self, channel_name: str):
```

**Change to:**
```python
def remove_channel(self, channel_name: str, log_index: Optional[int] = None):
    """
    Remove channel from plot.

    Args:
        channel_name: Channel to remove
        log_index: If specified, remove only this log's version.
                   If None, remove from all logs.
    """
    if log_index is not None:
        # Remove specific log
        plot_key = (channel_name, log_index)
        if plot_key in self.plot_items:
            self.plot_widget.removeItem(self.plot_items[plot_key]['plot_item'])
            del self.plot_items[plot_key]
    else:
        # Remove all logs
        keys_to_remove = [k for k in self.plot_items.keys() if k[0] == channel_name]
        for key in keys_to_remove:
            self.plot_widget.removeItem(self.plot_items[key]['plot_item'])
            del self.plot_items[key]
```

#### 6. Add NEW Method: `refresh_with_multi_log()`

Add this new method after `refresh_with_new_units()`:

```python
def refresh_with_multi_log(self, log_manager):
    """
    Refresh all plotted channels from current active logs.

    Args:
        log_manager: LogFileManager instance
    """
    if not self.plot_items:
        return

    # Collect unique channel names
    channel_names = set(key[0] for key in self.plot_items.keys())

    # Clear all
    self.clear_all_plots()

    # Re-plot from active logs
    for channel_name in channel_names:
        self.add_channel_from_all_logs(channel_name, log_manager)
```

#### 7. Update Other Methods That Reference `plot_items`

Search for all uses of `self.plot_items` and update them to handle tuple keys:

**In `clear_all_plots()`:** Should work as-is (just clears the dict)

**In `_auto_scale()`:** Update iteration:
```python
# OLD: for plot_info in self.plot_items.values():
# NEW: (should already work, but verify)
for plot_info in self.plot_items.values():
    plot_item = plot_info['plot_item']
    # ... rest of logic
```

**In legend double-click handler (eventFilter):** Update to handle tuple keys:
```python
# When finding channel to remove, search by channel name (first element of tuple)
for plot_key, plot_info in self.plot_items.items():
    if plot_key[0] == channel_name:  # plot_key is now (name, index)
        # Remove logic
```

### After Step 4:

**Step 5:** Fix any remaining issues with methods that iterate over `plot_items`

**Step 6:** Session persistence (v2.0 format) - can be done later, not blocking

**Step 7:** Testing and polish

## Key Architecture Reminders

- **Tuple keys:** `(channel_name, active_index)` allows same channel from different logs to coexist
- **Line styles:** Determined by position in active logs list (0=solid, 1=dash, 2=dot, 3=dashdot, 4=dashdotdot)
- **Color offset:** Each log gets different colors via `(base_idx + active_index * 2) % len(colors)`
- **Main log:** First checked log in the list - its channels appear in the channel tree
- **All active logs:** Clicking a channel in the tree plots it from ALL checked logs simultaneously

## How to Continue Next Session

**Start with:** "Continue implementing Step 4: Update plotting with line styles in plot_widget.py"

Then systematically work through the 7 sub-tasks listed above. The application will be functional once Step 4 is complete!

## Files Modified So Far

1. ✅ `mfviewer/data/log_manager.py` (NEW - 119 lines)
2. ✅ `mfviewer/widgets/log_list_widget.py` (NEW - 293 lines)
3. ✅ `mfviewer/gui/mainwindow.py` (MODIFIED - imports, __init__, _setup_ui, open_file, event handlers, etc.)
4. ⏳ `mfviewer/gui/plot_widget.py` (NEXT - needs updates described above)

## Testing After Step 4

Once plot_widget.py is updated:
1. Test syntax: `python -m py_compile mfviewer/gui/plot_widget.py`
2. Test run: `python run.py`
3. Load first log file - should appear in log list with checkbox checked
4. Load second log file - should appear below first log
5. Double-click a channel - should plot solid line from log 1, dashed line from log 2
6. Uncheck log 2 - should remove dashed lines, keep solid lines
7. Check log 2 again - should re-add dashed lines

Good luck! The foundation is solid. Step 4 is the key that makes it all work! 🚀
