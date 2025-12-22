# Dark Mode Styling

MFViewer now features a permanent dark mode theme inspired by modern IDEs like VS Code.

## Color Scheme

### Main Colors
- **Background**: `#2d2d30` (Medium dark gray)
- **Darker Background**: `#1e1e1e` (Very dark gray - used for plot area and tree)
- **Darkest Background**: `#191c1c` (Almost black - used for input fields)
- **Text**: `#dcdcdc` (Light gray)
- **Borders**: `#3e3e42` (Medium-dark gray)

### Accent Colors
- **Highlight**: `#2a82da` (Bright blue - for selections)
- **Active Accent**: `#007acc` (VS Code blue - for status bar and active elements)
- **Button**: `#0e639c` (Muted blue)
- **Button Hover**: `#1177bb` (Brighter blue)

### Plot Colors (Vibrant for dark backgrounds)
1. Bright Red: `#FF5A5A`
2. Bright Blue: `#5AC8FF`
3. Bright Green: `#64FF64`
4. Bright Orange: `#FFC85A`
5. Bright Purple: `#DC78FF`
6. Bright Cyan: `#5AF0DC`
7. Bright Pink: `#FF64C8`
8. Bright Yellow: `#F0F064`

## Styled Components

### Main Window
- Window background
- Menu bar with hover effects
- Toolbar
- Status bar (bright blue background)

### Widgets
- Tree widget (channel list)
- Tab widget with active tab indicator
- List widget (active plots)
- Buttons with hover and pressed states
- Splitter handles

### Plot Area
- Dark background (`#1e1e1e`)
- Light text for axes
- Subtle grid lines
- Dark legend background

## Implementation

The dark theme is applied in [mfviewer/gui/mainwindow.py](mfviewer/gui/mainwindow.py:38-168) using:
1. QPalette for global widget colors
2. QStyleSheet for fine-grained control
3. PyQtGraph settings for plot styling

All styling is automatic - no user configuration needed.
