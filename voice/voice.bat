@echo off
REM Voice bot, one entry point (Windows). Run from anywhere:  voice\voice.bat <command>
REM
REM   voice local         LOCAL TEST: stub BE + voice server + browser (nothing else needed)
REM   voice local --fake  same, without speech models (page/flow test only)
REM   voice real          REAL flow component: checks the BE, waits for it, serves on :8003
REM                       (the full three-machine flow is still:  python entrypoint\avvia.py)
REM   voice doctor        why does it not work? (this machine + the BE)
REM   voice v2 [--text]   on-demand voice chat from this PC
REM   voice live [url]    live call from this PC (no browser)
REM   voice test          run the voice test suite
setlocal
set "HERE=%~dp0"
set "PY=%HERE%..\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
set "PYTHONPATH=%HERE%src;%PYTHONPATH%"
set "VOICE_SETUP_SKIP=1"
if /i "%~1"=="test" (
    pushd "%HERE%"
    "%PY%" -m pytest tests -q %2 %3 %4 %5
    popd
    exit /b %errorlevel%
)
if "%~1"=="" (
    "%PY%" -m voicebot --help
    exit /b 0
)
"%PY%" -m voicebot %*
