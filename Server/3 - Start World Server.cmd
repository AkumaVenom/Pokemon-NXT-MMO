@echo off
setlocal
cd /d "%~dp0"
title Pokemon NXT MMO - World Server
if not exist ".venv\Scripts\python.exe" (
 echo Run 1 - Install Server Dependencies.cmd first.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" -u server.py --config "%~dp0config.ini"
if errorlevel 1 (
 echo.
 echo World server exited with an error. Read logs\world.log.
 pause
 exit /b 1
)
echo World stopped cleanly.
pause
