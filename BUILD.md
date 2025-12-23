# MFViewer Build Guide

This document describes how to build MFViewer as a standalone Windows executable and installer.

## Prerequisites

### Required Software

1. **Python 3.8 or higher**
   - Download from: https://www.python.org/downloads/

2. **Inno Setup 6** (for creating installers)
   - Download from: https://jrsoftware.org/isdl.php
   - Install to default location: `C:\Program Files (x86)\Inno Setup 6\`

### Python Dependencies

Install build dependencies:

```bash
pip install -r requirements.txt
pip install -r requirements-build.txt
```

Or use the virtual environment:

```bash
venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-build.txt
```

## Build Methods

### Quick Development Build

For testing the executable without creating an installer:

```bash
build_dev.bat
```

This will:
- Activate the virtual environment
- Install PyInstaller if needed
- Build the standalone executable
- Output: `dist\MFViewer.exe`

### Full Build with Installer

To create both the executable and Windows installer:

```bash
build.bat
```

This will:
- Activate the virtual environment
- Install PyInstaller if needed
- Build the standalone executable
- Create the Windows installer using Inno Setup
- Output:
  - `dist\MFViewer.exe` (standalone executable)
  - `dist\MFViewer-Setup-0.3.1.exe` (installer)

**Note:** If Inno Setup is not found, the script will create the executable but skip the installer creation.

## Manual Build Steps

If you prefer to build manually:

### 1. Build the Executable

```bash
venv\Scripts\activate
pyinstaller mfviewer.spec --clean
```

### 2. Create the Installer (Optional)

```bash
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
```

## Build Artifacts

After a successful build, you'll find:

- `dist\MFViewer.exe` - Standalone executable (can be run directly)
- `dist\MFViewer-Setup-0.3.1.exe` - Windows installer (if Inno Setup was used)

## Testing the Build

### Test the Executable

1. Navigate to the `dist` folder
2. Run `MFViewer.exe`
3. Verify:
   - Application launches with splash screen
   - All assets (logo, splash) load correctly
   - Config directory is created in `%LOCALAPPDATA%\MFViewer\MFViewer`
   - File operations work (open log files, save configurations)

### Test the Installer

For best results, test on a clean Windows machine or VM:

1. Run `MFViewer-Setup-0.3.1.exe`
2. Follow installation wizard
3. Verify:
   - Desktop shortcut created (if selected)
   - Start Menu entry created
   - Application installed to `C:\Program Files\MFViewer\`
   - Application launches correctly
   - Uninstaller works properly

## Build Configuration

### PyInstaller Spec File (`mfviewer.spec`)

Key configurations:
- **Single-file mode**: All dependencies bundled into one .exe
- **Console mode**: Disabled (GUI-only application)
- **Icon**: `Assets\MFViewer.ico`
- **Data files**: All assets from `Assets\` folder
- **UPX compression**: Enabled for smaller file size

### Inno Setup Script (`installer.iss`)

Key configurations:
- **App version**: 0.3.1 (update for each release)
- **Install directory**: `C:\Program Files\MFViewer\`
- **Desktop shortcut**: Optional (user selectable)
- **Start Menu entry**: Always created
- **Admin privileges**: Required for Program Files installation

## Updating Version Numbers

When creating a new release, update the version in:

1. `mfviewer\main.py` - `VERSION = "0.3.1"`
2. `installer.iss` - `AppVersion=0.3.1` and `OutputBaseFilename=MFViewer-Setup-0.3.1`
3. `README.md` - Download link and version references

## Troubleshooting

### PyInstaller Errors

**Problem:** Missing modules in bundled executable

**Solution:** Add missing imports to `hiddenimports` in `mfviewer.spec`

```python
hiddenimports=[
    'pandas',
    'numpy',
    'pyqtgraph',
    'openpyxl',
    'yaml',
    'platformdirs',
    # Add more if needed
],
```

**Problem:** Large executable size (>100MB)

**Solution:** Enable UPX compression (already enabled in spec file)

### Asset Loading Errors

**Problem:** Assets not found when running bundled executable

**Solution:** Ensure `get_resource_path()` helper is used for all asset paths

```python
def get_resource_path(relative_path: str) -> Path:
    if getattr(sys, 'frozen', False):
        base_path = Path(sys._MEIPASS)
    else:
        base_path = Path(__file__).parent.parent
    return base_path / relative_path
```

### Inno Setup Errors

**Problem:** ISCC.exe not found

**Solution:**
- Verify Inno Setup is installed
- Update path in `build.bat` if installed to non-default location
- Or run dev build only: `build_dev.bat`

## Creating a GitHub Release

1. Build the installer: `build.bat`
2. Test the installer thoroughly
3. Create a new tag: `git tag -a v0.3.1 -m "Release v0.3.1"`
4. Push tag: `git push origin v0.3.1`
5. Create GitHub release from tag
6. Upload `dist\MFViewer-Setup-0.3.1.exe` as release asset
7. Add release notes describing new features/fixes

## Notes

- The standalone executable is ~50-80MB due to bundled Python runtime and dependencies
- First launch may be slower as Windows Defender scans the executable
- Users may see SmartScreen warnings on unsigned executables (code signing certificate needed to prevent this)
- Configuration files are stored in `%LOCALAPPDATA%\MFViewer\MFViewer` (not in Program Files)
