@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "TASK_PY="
if exist "python.txt" set /p TASK_PY=<"python.txt"
if not defined TASK_PY set "TASK_PY=python"
if not "%~1"=="" goto :custom
"%TASK_PY%" "app\check_offline_scenes.py" --all --repair
goto :done
:custom
"%TASK_PY%" "app\check_offline_scenes.py" %*
:done
set "TASK_RESULT=%errorlevel%"
echo.
echo Scene checks finished. Reports are saved in each project's build\scene_audit folder.
pause
exit /b %TASK_RESULT%
