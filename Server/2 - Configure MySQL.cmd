@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"
title Pokemon NXT MMO - MySQL setup 1.1.0
echo.
echo Opening MySQL setup with editable password boxes.
echo ADMIN password means your EXISTING MySQL password, not a new one.
echo This never changes the MySQL root password or another game's database.
echo.
if not exist ".venv\Scripts\python.exe" (
 echo Run 1 - Install Server Dependencies.cmd first.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" setup_mysql.py --gui
if errorlevel 1 (
 echo.
 echo Setup was cancelled or did not complete. Read the message in the setup window.
 echo No administrator password was changed. A failed login does not replace config.ini.
 echo Console fallback: .venv\Scripts\python.exe setup_mysql.py --console
 pause
 exit /b 1
)
echo.
echo NXT MySQL setup completed.
echo For internet players, run 2b - Configure Online Hosting.cmd next.
echo Then start 3 - Start World Server.cmd.
pause
exit /b 0
