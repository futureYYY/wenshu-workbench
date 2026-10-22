@echo off
setlocal
cd /d "%~dp0.."
set "PY=backend\.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo Backend venv not found. See docs\07-packaging.md section 2.1.
  exit /b 1
)

tasklist /fi "imagename eq WenShu.exe" | find /i "WenShu.exe" >nul
if not errorlevel 1 (
  echo WenShu.exe is running. Quit it from the tray icon, then build again.
  goto :fail
)

echo [1/7] Backend tests
"%PY%" -m pytest backend\tests -q || goto :fail

echo [2/7] Frontend typecheck
pushd frontend
if not exist "node_modules" call :npm_install || (popd & goto :fail)
call npm run typecheck || (popd & goto :fail)
popd

echo [3/7] Frontend build into backend\app\static
call "scripts\build-web.bat" || goto :fail

echo [4/7] Version info
"%PY%" packaging\make_version_info.py || goto :fail
if not exist "packaging\icon.ico" (
  "%PY%" packaging\make_icon.py || goto :fail
)

rem Never let PyInstaller write into release: it deletes release\WenShu first, and with it
rem the data folder (jobs, settings, secret.key, saved API keys) of the packaged app.
echo [5/7] PyInstaller into build\dist
"%PY%" -m PyInstaller packaging\wenshu.spec --noconfirm --clean --distpath build\dist --workpath build\pyinstaller || goto :fail

echo [6/7] Self test
start "" /wait "build\dist\WenShu\WenShu.exe" --selftest
if errorlevel 1 (
  echo Self test failed. See build\dist\WenShu\data-selftest\logs\selftest.log
  goto :fail
)
rem A passing self test deletes data-selftest itself; make sure no data folder ends up in the zip
if exist "build\dist\WenShu\data-selftest" rmdir /s /q "build\dist\WenShu\data-selftest"
if exist "build\dist\WenShu\data" rmdir /s /q "build\dist\WenShu\data"

echo [7/7] Zip, then update release\WenShu and keep its data folder
if not exist "release" mkdir "release"
powershell -NoProfile -Command "Compress-Archive -Path 'build\dist\WenShu' -DestinationPath 'release\WenShu.zip' -Force" || goto :fail
rem Replace everything in release\WenShu except data and models.local.json (the local model config)
if exist "release\WenShu" (
  for /d %%D in ("release\WenShu\*") do if /i not "%%~nxD"=="data" rmdir /s /q "%%~fD"
  for %%F in ("release\WenShu\*") do if /i not "%%~nxF"=="models.local.json" del /q "%%~fF"
)
xcopy /e /i /q /y "build\dist\WenShu" "release\WenShu" >nul || goto :fail
echo Done: release\WenShu\WenShu.exe and release\WenShu.zip
exit /b 0

:fail
echo Build failed.
exit /b 1

:npm_install
rem npm ci needs package-lock.json; the very first install creates it with npm install
if exist "package-lock.json" (
  call npm ci
) else (
  call npm install
)
exit /b %errorlevel%
