@echo off
rem Starts the 2D Animation Studio GUI (no console window).
cd /d "%~dp0"
where pyw >nul 2>&1
if not errorlevel 1 (
  start "" pyw -3 "%~dp0app\studio_gui.py"
  exit /b 0
)
where pythonw >nul 2>&1
if not errorlevel 1 (
  start "" pythonw "%~dp0app\studio_gui.py"
  exit /b 0
)
echo Python was not found. Run Install-2D-Studio.cmd first.
pause
