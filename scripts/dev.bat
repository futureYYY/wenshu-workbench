@echo off
setlocal
cd /d "%~dp0.."
if exist "scripts\local.env.cmd" call "scripts\local.env.cmd"

if not exist "backend\.venv\Scripts\python.exe" (
  echo Backend venv not found. See docs\07-packaging.md section 2.1.
  exit /b 1
)

set "WENSHU_DEV=1"
set "WENSHU_PORT=18765"
set "WENSHU_DATA_DIR=%CD%\.devdata"
set "WENSHU_MOCK_FAIL_RATE=0.02"

rem The launcher binds its port in exclusive mode, but uvicorn sets SO_REUSEADDR and might still
rem bind the same port. Check first to give a clear message (docs\07-packaging.md section 3).
netstat -ano | findstr /r /c:":%WENSHU_PORT% .*LISTENING" >nul
if not errorlevel 1 (
  echo Port %WENSHU_PORT% is already in use, probably by a running WenShu.
  echo Quit it from the tray icon, then run dev.bat again.
  exit /b 1
)

start "WenShu API" cmd /k "cd /d backend && .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port %WENSHU_PORT% --reload --reload-dir app"
start "WenShu Web" cmd /k "cd /d frontend && npm run dev"

echo API:  http://127.0.0.1:%WENSHU_PORT%/docs
echo Web:  http://127.0.0.1:5173
timeout /t 4 >nul
start "" http://127.0.0.1:5173
