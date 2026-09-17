@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Pokemon NXT MMO - Automatic Source Build
echo.
echo ================================================================
echo   POKEMON NXT MMO - AUTOMATIC ALL-IN-ONE SOURCE BUILD 1.4.1
echo   Missing Go + Python + build packages are installed automatically
echo   Gameplay 0.6.10-alpha - Item gameplay repair
echo ================================================================
echo.
echo Extract the entire package first. An internet connection is needed
echo for missing downloads. No ROM, winget, Chocolatey or admin login needed.
echo Go is kept in your user tool cache. Missing Python is installed for
echo your Windows user, with pip and the MySQL password-window support.
echo Extracted music, cries and effects are included; no audio tools are needed.
echo This does NOT install MySQL or change databases, passwords or game settings.
echo.
if not exist "%~dp0Build\bootstrap_windows.ps1" goto incomplete
if not exist "%~dp0Build\bootstrap_lib.ps1" goto incomplete
if not exist "%~dp0Build\toolchains.json" goto incomplete
if not exist "%~dp0Build\build.py" goto incomplete
set "NXT_POWERSHELL=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if exist "%SystemRoot%\Sysnative\WindowsPowerShell\v1.0\powershell.exe" set "NXT_POWERSHELL=%SystemRoot%\Sysnative\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%NXT_POWERSHELL%" goto no_powershell
rem ExecutionPolicy applies ONLY to this child process; no policy is persisted.
rem Windows/organization security policies are not changed or disabled.
"%NXT_POWERSHELL%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Build\bootstrap_windows.ps1" %*
set "BUILD_RESULT=%ERRORLEVEL%"
echo.
if not "%BUILD_RESULT%"=="0" goto failed
echo BUILD SUCCEEDED. Open dist\LATEST_BUILD.txt for the new output folder.
echo Follow Docs\QUICK_START.md in that output to configure the world server.
goto finish
:failed
echo BUILD FAILED. Read the visible error and .build\logs in the source folder.
echo Correct a blocked connection or reported error, then run this BAT again.
echo Valid downloads are cached. No incomplete release was published.
goto finish
:incomplete
echo Incomplete source folder. Extract the FULL source ZIP, not just this BAT.
set "BUILD_RESULT=1"
goto finish
:no_powershell
echo Windows PowerShell 5.1 was not found in the Windows system folder.
echo This package targets normal Windows 10/11 x64 installations.
set "BUILD_RESULT=1"
:finish
if not "%NXT_BUILD_NO_PAUSE%"=="1" pause
exit /b %BUILD_RESULT%
