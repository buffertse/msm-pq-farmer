@echo off
title MSM PQ Farmer (CLI)

python --version >nul 2>&1
if errorlevel 1 (
    echo  Python hittas inte. Installera fran https://python.org
    pause & exit /b 1
)

pip install -r "%~dp0requirements.txt" --quiet 2>nul
python "%~dp0main.py" --cli %*
pause
