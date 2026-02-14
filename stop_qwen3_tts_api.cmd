@echo off
setlocal

set "PORT=10102"
set "PID="

for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%PORT% .*LISTENING"') do (
  set "PID=%%P"
  goto :kill
)

echo [INFO] Port %PORT% is not listening.
exit /b 0

:kill
echo [INFO] Stopping PID %PID% on port %PORT%...
taskkill /PID %PID% /F >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Failed to stop PID %PID%.
  exit /b 1
)

echo [INFO] Stopped.
endlocal
