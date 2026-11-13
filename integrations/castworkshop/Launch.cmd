@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYEXE=%~dp0runtime\python-cast\python.exe"
if exist "%PYEXE%" goto :run
set "PYEXE=%~dp0..\..\.venv\Scripts\python.exe"
if exist "%PYEXE%" goto :run
py -3.12 "%~dp0portable.py" %*
goto :done
:run
"%PYEXE%" -I "%~dp0portable.py" %*
:done
if errorlevel 1 echo Operation stopped. Read the message above.
pause
