@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist "cli.py" (
  echo ERROR: cli.py was not found.
  echo Copy this file and studio_bridge.py beside Sedabot's cli.py.
  pause
  exit /b 1
)
if not exist "studio_bridge.py" (
  echo ERROR: studio_bridge.py was not found.
  pause
  exit /b 1
)
python studio_bridge.py
if errorlevel 1 (
  echo.
  echo Bridge stopped. Check the message above.
  pause
)
