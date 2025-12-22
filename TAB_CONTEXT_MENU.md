# Tab Context Menu

Quick reference for the right-click tab menu in MFViewer.

## Accessing the Menu

**Right-click on any tab** to open the context menu with quick tab actions.

## Menu Options

### 1. Rename Tab
- **Action**: Opens a dialog to rename the current tab
- **Shortcut**: F2 (or double-click tab)
- **Use Case**: Give tabs descriptive names like "Engine", "Fuel System", etc.

### 2. New Tab
- **Action**: Creates a new plot tab
- **Shortcut**: Ctrl+T (or click "+" button)
- **Use Case**: Add another tab to organize different channel groups

### 3. Close Tab
- **Action**: Closes the selected tab
- **Shortcut**: Ctrl+W (or click "×" button)
- **State**: Disabled if it's the last remaining tab
- **Protection**: Always keeps at least one tab open

## Visual Design

The context menu uses MFViewer's dark theme:
- Dark background (#2d2d30)
- Light text (#dcdcdc)
- Blue highlight on hover (#2a82da)
- Consistent with main menu styling

## Usage Workflow

### Quick Rename
```
1. Right-click tab
2. Click "Rename Tab"
3. Enter new name
4. Press Enter
```

### Quick Close
```
1. Right-click tab you want to close
2. Click "Close Tab"
3. Tab closes immediately (no confirmation)
```

### Quick New Tab
```
1. Right-click any tab
2. Click "New Tab"
3. New tab created and becomes active
```

## Comparison with Other Methods

| Action | Right-Click | Alternative |
|--------|-------------|-------------|
| Rename | Right-click → Rename | Double-click tab or F2 |
| Close | Right-click → Close | Click "×" or Ctrl+W |
| New | Right-click → New | Click "+" or Ctrl+T |

## Tips

1. **Context-Aware**: Right-click directly on the tab you want to modify
2. **Visual Feedback**: Menu appears under cursor for easy access
3. **Keyboard Combo**: Right-click + Enter = Quick rename
4. **Consistency**: Same actions available in View menu and shortcuts

## Disabled States

The "Close Tab" option is **disabled** when:
- Only one tab remains open
- Visual indicator: Grayed out text
- Reason: MFViewer must always have at least one tab

## Advantages

**Compared to Double-Click:**
- More discoverable for new users
- Access to multiple actions in one place
- Works even if double-click is difficult

**Compared to Keyboard Shortcuts:**
- Visual menu shows all available actions
- No need to memorize shortcuts
- Mouse-based workflow

**Compared to Menu Bar:**
- Faster access (no need to navigate menus)
- Context-specific to the clicked tab
- Less mouse travel

## Future Enhancements

Potential future context menu options:
- [ ] Duplicate tab
- [ ] Close other tabs
- [ ] Close all tabs to the right
- [ ] Move tab to new window
- [ ] Pin tab
- [ ] Tab color/icon
