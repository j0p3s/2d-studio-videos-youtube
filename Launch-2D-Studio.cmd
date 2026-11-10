@echo off
setlocal EnableExtensions
rem Starts the 2D Animation Studio GUI (no console window) with the Python the installer chose.
cd /d "%~dp0"
set "PYEXE="
if exist "%~dp0python.txt" set /p PYEXE=<"%~dp0python.txt"
if not defined PYEXE goto :fallback
set "PYWEXE=%PYEXE:python.exe=pythonw.exe%"
if not exist "%PYWEXE%" goto :fallback
"%PYEXE%" "%~dp0app\portable_paths.py"
if errorlevel 1 exit /b 1
start "" "%PYWEXE%" "%~dp0app\studio_gui.py"
exit /b 0

:fallback
where pyw >nul 2>&1
if errorlevel 1 goto :plain
py -3.12 "%~dp0app\portable_paths.py"
if errorlevel 1 exit /b 1
start "" pyw -3.12 "%~dp0app\studio_gui.py"
exit /b 0

:plain
where pythonw >nul 2>&1
if errorlevel 1 goto :nopy
python "%~dp0app\portable_paths.py"
if errorlevel 1 exit /b 1
start "" pythonw "%~dp0app\studio_gui.py"
exit /b 0

:nopy
echo Python was not found. Run Install-2D-Studio.cmd first.
pause
