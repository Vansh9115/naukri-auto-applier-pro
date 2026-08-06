@echo off
title Naukri Auto-Applier Pro - Installer
cd /d "%~dp0"

echo ===================================================
echo   🚀 Naukri Auto-Applier Pro - Setup Installer
echo ===================================================
echo.

:: 1. Check Python availability
set PYTHON_CMD=
python --version >nul 2>&1
if %errorlevel%==0 (
    set PYTHON_CMD=python
) else (
    py --version >nul 2>&1
    if %errorlevel%==0 (
        set PYTHON_CMD=py
    )
)

if "%PYTHON_CMD%"=="" (
    echo [X] Python was NOT found on this computer.
    echo.
    echo Please install Python 3.10 or higher.
    echo IMPORTANT: Make sure to check "Add python.exe to PATH" during installation!
    echo.
    echo Opening Python download page in your browser...
    start https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

echo [1/3] Found Python (%PYTHON_CMD%). Installing required packages...
%PYTHON_CMD% -m pip install --upgrade pip
%PYTHON_CMD% -m pip install flask playwright werkzeug dulwich

echo.
echo [2/3] Installing Playwright Chromium browser...
%PYTHON_CMD% -m playwright install chromium

echo.
echo [3/3] Setting up workspace directories...
if not exist uploads mkdir uploads
if not exist naukri_chrome_profile mkdir naukri_chrome_profile

echo.
echo ===================================================
echo   ✅ Setup Completed Successfully!
echo   Double-click 'run_web_app.bat' to start the app.
echo ===================================================
echo.
pause
