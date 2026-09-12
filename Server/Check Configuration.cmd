@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Run 1 - Install Server Dependencies.cmd first.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" doctor.py
pause
