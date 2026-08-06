@echo off
title Naukri Auto-Applier Pro - Web Application
cd /d "%~dp0"

echo ===================================================
echo   🚀 Naukri Auto-Applier Pro
echo   Starting server at http://localhost:5000
echo ===================================================
echo.

:: Detect Python
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
    echo [X] Python is not installed or not in PATH!
    echo Please run 'install.bat' first to complete setup.
    echo.
    pause
    exit /b 1
)

%PYTHON_CMD% web_app.py
pause
