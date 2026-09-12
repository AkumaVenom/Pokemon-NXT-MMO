@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
title Pokemon NXT MMO - Server dependency setup
echo.
echo Pokemon NXT MMO - dedicated server setup
echo Only this Server folder receives packages. No database is modified.
echo The all-in-one build installs Python automatically when it is missing.
echo.
if exist ".venv\Scripts\python.exe" goto install
if defined NXT_PYTHON goto custompython
if exist "%LOCALAPPDATA%\Programs\PokemonNXT\Python313\python.exe" goto managedpython
where py >nul 2>nul
if errorlevel 1 goto plainpython
py -3 -c "import sys,struct; raise SystemExit(0 if sys.version_info >= (3,11) and struct.calcsize('P')==8 else 1)"
if errorlevel 1 goto missing
py -3 -m venv .venv
if errorlevel 1 goto failed
goto install
:managedpython
set "NXT_PYTHON=%LOCALAPPDATA%\Programs\PokemonNXT\Python313\python.exe"
goto custompython
:custompython
"%NXT_PYTHON%" -I -c "import sys,struct,ssl,venv,ensurepip,tkinter; sys.exit(0 if sys.version_info >= (3,11) and struct.calcsize('P')==8 else 1)"
if errorlevel 1 goto missing
"%NXT_PYTHON%" -m venv .venv
if errorlevel 1 goto failed
goto install
:plainpython
where python >nul 2>nul
if errorlevel 1 goto missing
python -c "import sys,struct; raise SystemExit(0 if sys.version_info >= (3,11) and struct.calcsize('P')==8 else 1)"
if errorlevel 1 goto missing
python -m venv .venv
if errorlevel 1 goto failed
:install
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo.
echo Dependencies installed. Next run 2 - Configure MySQL.cmd.
echo For an explicit local-only developer test, use Start Developer SQLite World.cmd.
pause
exit /b 0
:missing
echo.
echo Python 3.11 or newer, 64-bit, was not found or NXT_PYTHON is invalid.
echo The source BUILD_ALL.bat automatically installs missing Python and Go.
echo On a server-only PC, install full Python x64 from python.org first,
echo or set NXT_PYTHON to its complete python.exe path. Then rerun this script.
pause
exit /b 1
:failed
echo.
echo Setup failed. Read the error above. No system-wide packages were installed.
pause
exit /b 1
