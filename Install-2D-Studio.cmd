@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
title 2D Animation Studio - Installer
color 0A

rem ==========================================================================
rem  2D Animation Studio installer
rem  Installs: Git, Node.js LTS, Python 3.12, FFmpeg, Claude Code CLI,
rem            GrowKaz Stickman Studio (three.js + Playwright Chromium),
rem            Python libs (numpy, scipy, faster-whisper, edge-tts, piper-tts, YouTube API,
rem            customtkinter, pillow), the plugin skills + ScriptForge skill,
rem            the Whisper speech model and a Piper voice (so timestamps and
rem            voiceover work with no internet),
rem            all studio settings beside this installer.
rem  Optional: offline mode - Ollama and a local AI model (about 15 GB).
rem            Codex and the Gemini CLI are installed from the GUI Setup page.
rem  Safe to run again: it skips what is already installed and never touches
rem  your projects\ folder.
rem ==========================================================================

set "SRC=%~dp0"
if "%SRC:~-1%"=="\" set "SRC=%SRC:~0,-1%"
set "HOME2D=%SRC%"
set "STUDIO=%HOME2D%\growkaz-stickman-studio"
set "SKILLS=%HOME2D%\.claude\skills"
set "npm_config_prefix=%HOME2D%\.tools"
set "npm_config_cache=%HOME2D%\.cache\npm"
set "PIP_CACHE_DIR=%HOME2D%\.cache\pip"
set "PLAYWRIGHT_BROWSERS_PATH=%HOME2D%\.cache\playwright"
set "HF_HOME=%HOME2D%\.cache\huggingface"
set "TEMP=%HOME2D%\.runtime\tmp"
set "TMP=%TEMP%"
if not exist "%TEMP%" mkdir "%TEMP%"
set "PATH=%HOME2D%\.tools;%PATH%"

echo.
echo  ===========================================================
echo     2D ANIMATION STUDIO  -  one-click installer
echo  ===========================================================
echo   Install folder : %HOME2D%
echo   Local skills  : %SKILLS%
echo.
echo   This will install (if missing): Git, Node.js, Python, FFmpeg,
echo   Claude Code, Chromium (headless), and about 1.5 GB of tools.
echo   It then offers the optional offline mode (Ollama, about 15 GB).
echo.
pause

if not exist "%HOME2D%" mkdir "%HOME2D%"

rem ---------- 0. winget -------------------------------------------------------
where winget >nul 2>&1
if errorlevel 1 (
  echo.
  echo  [X] winget was not found. Install "App Installer" from the Microsoft Store,
  echo      then run this installer again.
  start "" "ms-windows-store://pdp/?productid=9NBLGGH4NNS1"
  pause
  exit /b 1
)

rem ---------- 1. System tools -------------------------------------------------
call :banner "1/8  System tools (Git, Node.js, FFmpeg)"
call :ensure git    Git.Git
call :ensure node   OpenJS.NodeJS.LTS
call :ensure ffmpeg Gyan.FFmpeg

call :banner "2/8  Python 3.12"
set "PY="
call :findpy
if not defined PY (
  echo   installing Python 3.12 ...
  winget install --id Python.Python.3.12 -e --silent --accept-package-agreements --accept-source-agreements --override "/quiet InstallAllUsers=0 PrependPath=0 Include_launcher=1 Include_tcltk=1 Include_pip=1"
  call :refresh
  call :findpy
)
if not defined PY (
  echo  [X] Python could not be found after install. Close this window, open a new one and run the installer again.
  pause
  exit /b 1
)
echo   [ok] Python: %PY%

rem ---------- 3. Claude Code --------------------------------------------------
call :banner "3/8  Claude Code CLI"
call :findclaude
if not defined CLAUDE_OK (
  echo   installing Claude Code into the local .tools folder ...
  call npm install --prefix "%HOME2D%\.tools" -g @anthropic-ai/claude-code
  call :findclaude
)
if defined CLAUDE_OK (echo   [ok] Claude Code found) else (echo   [!] Claude Code not found - the GUI Setup page can retry this.)
echo   [info] Codex and Gemini are optional alternatives: install and sign in from GUI Setup.
echo   [info] Gemini API needs GEMINI_API_KEY in the .env file beside this installer.
echo   [info] Higgsfield (AI video shots) needs HIGGSFIELD_API_KEY=key-id:key-secret there too.
if not exist "%HOME2D%\.env" (
  >"%HOME2D%\.env" echo # Keys and defaults for the studio. This file stays on this PC.
  >>"%HOME2D%\.env" echo # GEMINI_API_KEY=
  >>"%HOME2D%\.env" echo # GEMINI_MODEL=gemini-3.5-flash
  >>"%HOME2D%\.env" echo # OLLAMA_MODEL=gpt-oss:20b
  >>"%HOME2D%\.env" echo # HIGGSFIELD_API_KEY=key-id:key-secret
  echo   [ok] created .env ^(add your keys there^)
)

rem ---------- 4. Copy app + plugin --------------------------------------------
call :banner "4/8  App, GrowKaz Stickman plugin and ScriptForge skill"
set "PLUG=%SRC%\plugin\GrowKaz_Stickman.plugin"
if not exist "%PLUG%" set "PLUG=%USERPROFILE%\Downloads\GrowKaz_Stickman.plugin"
if not exist "%PLUG%" (
  echo  [X] GrowKaz_Stickman.plugin not found. Put it in "%SRC%\plugin\" or in Downloads.
  pause
  exit /b 1
)
set "EXT=%TEMP%\growkaz_plugin_%RANDOM%"
mkdir "%EXT%"
tar -xf "%PLUG%" -C "%EXT%"
if not exist "%EXT%\skills\make-2d-video\kit\render.mjs" (
  echo  [X] The plugin file could not be unpacked.
  pause
  exit /b 1
)

rem The app already lives beside this installer; do not copy it to the user profile.
%PY% "%HOME2D%\app\portable_paths.py"
if errorlevel 1 exit /b 1

rem studio kit (never overwrites projects\)
robocopy "%EXT%\skills\make-2d-video\kit" "%STUDIO%" /E /XD projects /NFL /NDL /NJH /NJS /NP >nul
if not exist "%STUDIO%\projects" mkdir "%STUDIO%\projects"
rem let the renderer use installed Chrome/Edge when Playwright's Chromium download is blocked
%PY% "%HOME2D%\app\patch_kit.py" "%STUDIO%"
echo   [ok] studio kit  -^> %STUDIO%

rem Local Claude Code skills (the plugin's 5 skills + ScriptForge)
if not exist "%SKILLS%" mkdir "%SKILLS%"
for %%S in (make-2d-video new-video render-video video-sound video-styles) do (
  robocopy "%EXT%\skills\%%S" "%SKILLS%\%%S" /E /NFL /NDL /NJH /NJS /NP >nul
)
robocopy "%SRC%\app\skills\scriptforge" "%SKILLS%\scriptforge" /E /NFL /NDL /NJH /NJS /NP >nul
echo   [ok] skills: make-2d-video, new-video, render-video, video-sound, video-styles, scriptforge
rmdir /s /q "%EXT%" 2>nul

rem ---------- 5. Node packages + Chromium -------------------------------------
call :banner "5/8  three.js, Playwright and headless Chromium"
pushd "%STUDIO%"
call npm install --no-fund --no-audit
echo.
echo   Using installed Chrome/Edge. Any browser download uses this folder's .cache.
rem Installed Chrome/Edge is preferred; no shared browser download.
popd

rem ---------- 6. Python packages ----------------------------------------------
call :banner "6/8  Python packages"
%PY% -m venv --system-site-packages "%HOME2D%\.venv"
if errorlevel 1 exit /b 1
set PY="%HOME2D%\.venv\Scripts\python.exe"
%PY% -m pip install --upgrade numpy scipy faster-whisper edge-tts piper-tts customtkinter pillow google-api-python-client google-auth-oauthlib google-auth-httplib2
%PY% -c "import sys, pathlib; pathlib.Path(r'%HOME2D%\python.txt').write_text(r'.venv\Scripts\python.exe')"
echo   downloading the Whisper speech model (about 500 MB, once) ...
%PY% -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8')"
if errorlevel 1 (echo   [!] Whisper model not downloaded - it will download on the first video instead.) else (echo   [ok] Whisper model ready for offline use)
echo   downloading the Piper offline voice (about 120 MB, once) ...
if not exist "%HOME2D%\.cache\piper\en_US-ryan-high.onnx" %PY% -m piper.download_voices --download-dir "%HOME2D%\.cache\piper" en_US-ryan-high
if exist "%HOME2D%\.cache\piper\en_US-ryan-high.onnx" (echo   [ok] Piper voice ready for offline use) else (echo   [!] Piper voice not downloaded - it will download on the first offline voiceover instead.)

rem ---------- 7. Offline mode (optional) --------------------------------------
call :banner "7/8  Offline mode (optional): Ollama + local AI model"
set "OLLAMA_MODEL=gpt-oss:20b"
call :findollama
if defined OLLAMA_EXE (
  echo   [ok] Ollama already installed
) else (
  echo   Offline mode lets the studio work with no internet and no AI credits.
  echo   It needs Ollama ^(about 1 GB^) and a local model ^(%OLLAMA_MODEL%, about 14 GB^).
  choice /c YN /t 30 /d N /m "Install Ollama now (N is chosen after 30 seconds)"
  if errorlevel 2 goto :offline_done
  winget install --id Ollama.Ollama -e --silent --accept-package-agreements --accept-source-agreements
  call :refresh
  call :findollama
)
if not defined OLLAMA_EXE (
  echo   [!] Ollama not found - use "Install Ollama" on the GUI Setup page later.
  goto :offline_done
)
"%OLLAMA_EXE%" show %OLLAMA_MODEL% >nul 2>&1
if not errorlevel 1 (
  echo   [ok] offline model %OLLAMA_MODEL% already downloaded
  goto :offline_done
)
choice /c YN /t 30 /d N /m "Download the offline model %OLLAMA_MODEL% now, about 14 GB (N after 30 seconds)"
if errorlevel 2 (
  echo   [info] skipped - use "Download offline model" on the GUI Setup page later.
  goto :offline_done
)
"%OLLAMA_EXE%" pull %OLLAMA_MODEL%
if errorlevel 1 (echo   [!] model download failed - retry from the GUI Setup page.) else (echo   [ok] offline model ready)
:offline_done

rem ---------- 8. Check ---------------------------------------------
call :banner "8/8  Checking everything"
pushd "%STUDIO%"
%PY% tools\verify_kit.py
%PY% tools\doctor.py
popd

echo.
echo  ===========================================================
echo    DONE!  Run Launch-2D-Studio.cmd in this folder.
echo.
echo    First time only:
echo     - Setup page ^> choose Claude, OpenAI Codex or Gemini and sign in.
echo     - Upload page ^> "YouTube setup" to connect your channel.
echo     - No internet or no AI credits left? Setup page ^> "Always work offline".
echo  ===========================================================
echo.
choice /c YN /m "Open the studio now"
if errorlevel 2 goto :eof
call "%HOME2D%\Launch-2D-Studio.cmd"
goto :eof

rem ==========================================================================
:banner
echo.
echo  -----------------------------------------------------------
echo   %~1
echo  -----------------------------------------------------------
exit /b 0

:ensure
where %1 >nul 2>&1
if not errorlevel 1 (
  echo   [ok] %1 already installed
  exit /b 0
)
echo   installing %2 ...
winget install --id %2 -e --silent --accept-package-agreements --accept-source-agreements
call :refresh
where %1 >nul 2>&1
if errorlevel 1 (echo   [!] %1 still not on PATH - open a new window and re-run if later steps fail) else (echo   [ok] %1 installed)
exit /b 0

:findpy
rem faster-whisper has no packages for very new Pythons (3.14+), so prefer 3.12 / 3.11 / 3.13 / 3.10
set "PY="
where py >nul 2>&1
if errorlevel 1 goto :findpy_plain
for %%V in (3.12 3.11 3.13 3.10) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
  )
)
if defined PY exit /b 0
:findpy_plain
python -c "import sys; sys.exit(0 if (3,9) <= sys.version_info[:2] <= (3,13) else 1)" >nul 2>&1
if not errorlevel 1 set "PY=python"
exit /b 0

:findclaude
set "CLAUDE_OK="
where claude >nul 2>&1
if not errorlevel 1 set "CLAUDE_OK=1"
if exist "%USERPROFILE%\.local\bin\claude.exe" set "CLAUDE_OK=1"
exit /b 0

:findollama
set "OLLAMA_EXE="
for /f "delims=" %%O in ('where ollama 2^>nul') do if not defined OLLAMA_EXE set "OLLAMA_EXE=%%O"
if not defined OLLAMA_EXE if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
exit /b 0

:refresh
rem reload PATH from the registry so freshly installed tools are found
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('Path','Machine')+';'+[Environment]::GetEnvironmentVariable('Path','User')"`) do set "PATH=%HOME2D%\.tools;%%P;%USERPROFILE%\.local\bin"
exit /b 0
