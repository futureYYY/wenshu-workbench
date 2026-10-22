@echo off
setlocal
cd /d "%~dp0.."
if exist "scripts\local.env.cmd" call "scripts\local.env.cmd"
if not defined WENSHU_DATA_DIR set "WENSHU_DATA_DIR=%CD%\data"
rem Deleting backend\app\static under a running WenShu breaks its open window (404 on assets)
if exist "backend\.venv\Scripts\python.exe" (
  "backend\.venv\Scripts\python.exe" "scripts\prestart.py" --check-running
  if errorlevel 1 (
    echo WenShu is running from this folder. Quit it from the tray icon, then run build-web.bat again.
    exit /b 1
  )
)
pushd frontend
if not exist "node_modules" call :npm_install || (popd & exit /b 1)
call npm run build || (popd & exit /b 1)
popd
if exist "backend\app\static" rmdir /s /q "backend\app\static"
xcopy /e /i /q /y "frontend\dist" "backend\app\static" >nul || exit /b 1
if exist "backend\.venv\Scripts\python.exe" "backend\.venv\Scripts\python.exe" "scripts\prestart.py" --write-stamp
echo Frontend built into backend\app\static
exit /b 0

:npm_install
rem npm ci needs package-lock.json; the very first install creates it with npm install
if exist "package-lock.json" (
  call npm ci
) else (
  call npm install
)
exit /b %errorlevel%
