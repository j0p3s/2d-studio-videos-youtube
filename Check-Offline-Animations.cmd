@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "TASK_PY="
if exist "python.txt" set /p TASK_PY=<"python.txt"
if not defined TASK_PY set "TASK_PY=python"
set "TASK_REPORT=%~dp0reports\offline-animations"
if not exist "%TASK_REPORT%" mkdir "%TASK_REPORT%"
rem Replace stale results even if Python cannot start or argument parsing fails.
>"%TASK_REPORT%\index.html" echo ^<!doctype html^>^<html lang="en"^>^<meta charset="utf-8"^>^<title^>Offline check did not finish^</title^>^<h1^>No completed results for this run^</h1^>^<p^>The checker did not finish creating the report. See the console for the error or help text. Earlier results were replaced.^</p^>^</html^>
copy /y "%TASK_REPORT%\index.html" "%TASK_REPORT%\.index.html" >nul
if not "%~1"=="" goto :custom
"%TASK_PY%" "app\check_offline_scenes.py" --all --repair --report-dir "%TASK_REPORT%"
goto :done
:custom
"%TASK_PY%" "app\check_offline_scenes.py" %* --report-dir "%TASK_REPORT%"
:done
set "TASK_RESULT=%errorlevel%"
echo.
echo Report rebuilt: "%TASK_REPORT%\.index.html"
choice /c YN /n /m "Open the HTML report? [Y/N]: "
if errorlevel 2 goto :exit
start "" "%TASK_REPORT%\.index.html"
:exit
exit /b %TASK_RESULT%
