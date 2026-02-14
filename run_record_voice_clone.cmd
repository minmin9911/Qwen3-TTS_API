@echo off
setlocal

for %%I in ("%~dp0.") do set "ROOT=%%~fI"
set "PY=%ROOT%\.venv-qwen3tts\Scripts\python.exe"
set "SCRIPT=%ROOT%\tools\record\create_voice_clone_speaker.py"

if not exist "%PY%" (
  echo [ERROR] python not found: %PY%
  exit /b 1
)

if not exist "%SCRIPT%" (
  echo [ERROR] script not found: %SCRIPT%
  exit /b 1
)

cd /d "%ROOT%"

echo Enter speaker name. Example: masayuki_clone
set /p "NAME=> "
if "%NAME%"=="" (
  echo [ERROR] speaker name is empty.
  exit /b 1
)

"%PY%" "%SCRIPT%" --name "%NAME%"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo [ERROR] recording script failed. code=%RC%
  exit /b %RC%
)

echo [OK] done.
endlocal
