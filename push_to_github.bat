@echo off
title Push Naukri Auto-Applier Pro to GitHub
cd /d "%~dp0"
echo Starting GitHub Sync...
"C:\Users\vansh\AppData\Local\Python\bin\python3.14.exe" github_push.py
pause
