@echo off
echo ============================================
echo   Naukri Auto-Applier Pro - Installation
echo ============================================
echo.

echo [1/3] Installing Python packages...
pip install flask playwright 2>nul || python -m pip install flask playwright 2>nul || py -m pip install flask playwright
echo.

echo [2/3] Installing Playwright browsers...
python -m playwright install chromium 2>nul || py -m playwright install chromium
echo.

echo [3/3] Creating upload directory...
if not exist uploads mkdir uploads
echo.

echo ============================================
echo   Installation complete!
echo   Run 'run_web_app.bat' to start the app.
echo ============================================
pause
