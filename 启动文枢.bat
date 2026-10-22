@echo off
setlocal
cd /d "%~dp0"
if exist "scripts\local.env.cmd" call "scripts\local.env.cmd"
if not defined WENSHU_DATA_DIR set "WENSHU_DATA_DIR=%CD%\data"

if not exist "backend\.venv\Scripts\pythonw.exe" (
  call "scripts\setup.bat" || goto :fail
)

"backend\.venv\Scripts\python.exe" "scripts\prestart.py" || goto :fail

start "" /d "%CD%\backend" "%CD%\backend\.venv\Scripts\pythonw.exe" -m app.launcher
exit /b 0

:fail
echo.
echo WenShu could not start. Read the messages above, then press any key to close.
pause >nul
exit /b 1
