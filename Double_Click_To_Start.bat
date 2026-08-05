@echo off
title Naukri Auto-Applier Pro - Double Click To Start
cd /d "%~dp0"
echo ========================================================
echo   🚀 Starting Naukri Auto-Applier Pro Web Application
echo ========================================================
echo.
echo Checking environment...
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo Python is not installed in PATH. Attempting launching embedded runner...
    if exist "%LOCALAPPDATA%\Python\bin\python3.14.exe" (
        "%LOCALAPPDATA%\Python\bin\python3.14.exe" web_app.py
        goto end
    )
    echo Please ensure Python is installed or run in browser.
    pause
    exit /b
)

python web_app.py

:end
pause
