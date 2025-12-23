@echo off
REM Full build with installer
echo ========================================
echo MFViewer Full Build
echo ========================================
echo.

REM Activate virtual environment
call venv\Scripts\activate

REM Install PyInstaller if not present
pip install pyinstaller platformdirs

REM Build executable
echo.
echo Building standalone executable...
pyinstaller mfviewer.spec --clean

REM Check if Inno Setup is installed
if not exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    echo.
    echo WARNING: Inno Setup 6 not found!
    echo Please install Inno Setup from: https://jrsoftware.org/isdl.php
    echo Or update the path in this script.
    echo.
    echo Executable built successfully, but installer was not created.
    echo Executable: dist\MFViewer.exe
    echo.
    pause
    exit /b
)

REM Create installer
echo.
echo Creating installer...
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss

echo.
echo ========================================
echo Build complete!
echo ========================================
echo Executable: dist\MFViewer.exe
echo Installer: dist\MFViewer-Setup-0.3.1.exe
echo.
pause
