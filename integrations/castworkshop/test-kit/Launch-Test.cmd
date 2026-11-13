@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONUNBUFFERED=1"
set "PYEXE=%~dp0CastWorkshop\.venv\Scripts\python.exe"
if not exist "%PYEXE%" goto :fallback
"%PYEXE%" "%~dp0test_launcher.py" %*
goto :done
:fallback
py -3.12 "%~dp0test_launcher.py" %*
:done
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" echo Test stopped. See the logs folder and the message above.
if "%~1"=="--check" exit /b %RESULT%
pause
exit /b %RESULT%
