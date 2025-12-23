@echo off
REM Quick development build for testing (no installer)
echo ========================================
echo MFViewer Development Build
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

echo.
echo ========================================
echo Dev build complete!
echo ========================================
echo Executable: dist\MFViewer.exe
echo.
pause
