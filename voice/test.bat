@echo off
REM Test voice con una riga sola: da dentro voice\  ->  test.bat
set PYTHONPATH=src
set VOICE_SETUP_SKIP=1
if exist ..\.venv\Scripts\python.exe (
    ..\.venv\Scripts\python.exe -m pytest tests -q %*
) else (
    python -m pytest tests -q %*
)
