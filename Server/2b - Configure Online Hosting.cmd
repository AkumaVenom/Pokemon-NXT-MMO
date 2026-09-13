@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"
title Pokemon NXT MMO - Online Hosting Setup 1.2.2
echo.
echo Configure the public hostname and TLS certificate before online hosting.
echo Stop the world before saving. Your database settings are kept.
echo.
if not exist ".venv\Scripts\python.exe" (
 echo Run 1 - Install Server Dependencies.cmd first.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" setup_online.py --gui
if errorlevel 1 (
 echo.
 echo Online setup did not complete. Read the setup window or error above.
 echo Console alternative: .venv\Scripts\python.exe setup_online.py --console
 pause
 exit /b 1
)
echo.
echo Setup saved. Read its connection kit instructions, then start the world.
echo Each player needs matching Client config values and certificate trust.
pause
exit /b 0
