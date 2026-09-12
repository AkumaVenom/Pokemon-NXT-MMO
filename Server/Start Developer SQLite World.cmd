@echo off
setlocal
cd /d "%~dp0"
title Pokemon NXT MMO - DEVELOPER SQLITE TEST WORLD
echo.
echo This explicitly uses data\development.sqlite3, NOT MySQL.
echo Accounts here are SEPARATE from your MySQL world. No automatic migration occurs.
echo Intended for localhost smoke testing only.
echo.
if not exist ".venv\Scripts\python.exe" (
 echo Run 1 - Install Server Dependencies.cmd first.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" -u server.py --config "%~dp0config.ini" --dev-sqlite
pause
