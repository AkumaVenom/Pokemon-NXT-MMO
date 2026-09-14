@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
title Pokemon NXT MMO - World Server
if not exist ".venv\Scripts\python.exe" (
 echo Run 1 - Install Server Dependencies.cmd first.
 pause
 exit /b 1
)
:start_world
echo Starting Pokemon NXT MMO world server...
echo Startup diagnostics will show the full log path below.
echo.
".venv\Scripts\python.exe" -u server.py --config "%~dp0config.ini"
set "NXT_WORLD_RESULT=%ERRORLEVEL%"
if "%NXT_WORLD_RESULT%"=="75" (
 echo World saved and released its lease. Restarting as requested...
 goto start_world
)
if not "%NXT_WORLD_RESULT%"=="0" (
 echo.
 echo World server exited with an error. Read the cause and log path above.
 echo Run Check Configuration.cmd to diagnose the current settings.
 echo For missing TLS files, run 2b - Configure Online Hosting.cmd.
 pause
 exit /b %NXT_WORLD_RESULT%
)
echo World stopped cleanly.
pause
exit /b 0
