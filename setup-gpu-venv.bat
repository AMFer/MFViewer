@echo off
REM MFViewer GPU Environment Setup Script
REM This creates a Python 3.11 venv with full CUDA GPU acceleration
REM
REM Prerequisites:
REM   1. Install Python 3.11 from https://www.python.org/downloads/release/python-3119/
REM      OR run: py install 3.11
REM   2. NVIDIA GPU with CUDA support
REM   3. NVIDIA drivers installed

echo ============================================
echo MFViewer GPU Environment Setup
echo ============================================
echo.

REM Check if Python 3.11 is available
py -3.11 --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python 3.11 is not installed.
    echo.
    echo Please install Python 3.11:
    echo   Option 1: py install 3.11
    echo   Option 2: Download from https://www.python.org/downloads/release/python-3119/
    echo.
    pause
    exit /b 1
)

echo Found Python 3.11
py -3.11 --version
echo.

REM Create venv
echo Creating virtual environment (venv-gpu)...
py -3.11 -m venv venv-gpu
if errorlevel 1 (
    echo ERROR: Failed to create virtual environment
    pause
    exit /b 1
)

echo.
echo Activating virtual environment...
call venv-gpu\Scripts\activate.bat

echo.
echo Upgrading pip...
python -m pip install --upgrade pip -q

echo.
echo Installing core dependencies...
pip install -r requirements.txt -q

echo.
echo Installing CUDA GPU acceleration (CuPy)...
echo This may take a few minutes...
pip install cupy-cuda12x

if errorlevel 1 (
    echo.
    echo WARNING: CuPy installation failed.
    echo This could mean:
    echo   - CUDA 12.x is not installed
    echo   - Your GPU doesn't support CUDA
    echo.
    echo Trying CUDA 11.x version...
    pip install cupy-cuda11x

    if errorlevel 1 (
        echo.
        echo WARNING: CuPy installation failed for both CUDA 12 and 11.
        echo The application will still work using CPU-based Polars optimization.
    )
)

echo.
echo ============================================
echo Setup Complete!
echo ============================================
echo.
echo To use the GPU-accelerated environment:
echo   1. Activate: venv-gpu\Scripts\activate
echo   2. Run: python run.py
echo.
echo Current backend status:
python -c "from mfviewer.data.parser import get_parser_backend, POLARS_AVAILABLE, CUDF_AVAILABLE, PYARROW_AVAILABLE; from mfviewer.gui.plot_widget import CUPY_AVAILABLE; print(f'Parser: {get_parser_backend()}'); print(f'Polars: {POLARS_AVAILABLE}'); print(f'PyArrow: {PYARROW_AVAILABLE}'); print(f'cuDF: {CUDF_AVAILABLE}'); print(f'CuPy: {CUPY_AVAILABLE}')"
echo.
pause
