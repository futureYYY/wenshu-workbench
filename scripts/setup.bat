@echo off
setlocal
cd /d "%~dp0.."
if exist "scripts\local.env.cmd" call "scripts\local.env.cmd"

set "PYEXE="
if defined WENSHU_PYTHON if exist "%WENSHU_PYTHON%" set PYEXE="%WENSHU_PYTHON%"
if not defined PYEXE py -3.13 -c "import sys" >nul 2>nul && set "PYEXE=py -3.13"
if not defined PYEXE python -c "import sys; sys.exit(0 if sys.version_info >= (3, 13) else 1)" >nul 2>nul && set "PYEXE=python"
if not defined PYEXE (
  echo Python 3.13 was not found.
  echo Copy scripts\local.env.cmd.example to scripts\local.env.cmd and set WENSHU_PYTHON.
  exit /b 1
)

echo Creating backend\.venv ...
%PYEXE% -m venv "backend\.venv" || exit /b 1
exit /b 0
