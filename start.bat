@echo off
title MSM PQ Farmer

python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  Python is not installed.
    echo  Get it from https://python.org or the Microsoft Store.
    echo.
    pause & exit /b 1
)

pip show pillow  >nul 2>&1 || pip install pillow  --quiet 2>nul
pip show pywin32 >nul 2>&1 || pip install pywin32 --quiet 2>nul

python "%~dp0farmer.py" %*
pause
