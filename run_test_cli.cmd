@echo off
setlocal
chcp 65001 >nul

set "TEST_TEXT=こんにちは。これはテスト再生です。今日は良い天気ですね。よぉ。元気か？今日は天気よかったな。"
for %%I in ("%~dp0.") do set "ROOT=%%~fI"
set "CLI_DIR=%ROOT%\tools\cli"
set "CONFIG_PATH=%CLI_DIR%\config.yaml"

echo [1/3] Speaker一覧を取得します...
cd /d "%CLI_DIR%"
node src\index.js list --config "%CONFIG_PATH%"
if errorlevel 1 (
  echo Speaker一覧の取得に失敗しました。
  exit /b 1
)

echo.
set /p x=SpeakerIDを入力してください: 
if "%x%"=="" (
  echo SpeakerIDが未入力です。
  exit /b 1
)

echo.
echo [2/3] SpeakerID=%x% でテスト再生します...
node src\index.js play --config "%CONFIG_PATH%" --speaker-id "%x%" --text "%TEST_TEXT%"
if errorlevel 1 (
  echo 再生に失敗しました。
  exit /b 1
)

echo.
echo [3/3] 完了しました。
endlocal
