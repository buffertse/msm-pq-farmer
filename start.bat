@echo off
title MSM PQ Farmer
color 0A

echo.
echo  =============================================
echo     MSM PQ Farmer - MapleStory Idle RPG
echo  =============================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  [!] Python hittas inte.
    echo.
    echo  Installera Python fran:
    echo    https://python.org
    echo    eller Microsoft Store (sok "Python 3.12")
    echo.
    echo  VIKTIGT: Kryssa i "Add Python to PATH" vid installation!
    echo.
    pause
    exit /b 1
)

echo  [1/2] Installerar paket (forsta gangen kan ta en stund)...
pip install -r "%~dp0requirements.txt" --quiet 2>nul
if errorlevel 1 (
    echo  [!] Kunde inte installera paket. Testar ett i taget...
    pip install pillow --quiet 2>nul
    pip install pywin32 --quiet 2>nul
    pip install opencv-python --quiet 2>nul
    pip install numpy --quiet 2>nul
    pip install pyyaml --quiet 2>nul
)

echo  [2/2] Startar...
echo.

python "%~dp0main.py" %*

if errorlevel 1 (
    echo.
    echo  [!] Nagot gick fel. Se felmeddelandet ovan.
    echo.
)
pause
