@echo off
setlocal
for %%I in ("%~dp0.") do set "ROOT=%%~fI"
set "PY=%ROOT%\.venv-qwen3tts\Scripts\python.exe"

if not exist "%PY%" (
  echo [ERROR] python not found: %PY%
  exit /b 1
)

"%PY%" -m uvicorn api.main:app --host 127.0.0.1 --port 10102 --app-dir "%ROOT%" --log-level debug --access-log
endlocal
