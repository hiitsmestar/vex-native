@echo off
setlocal
title Vex Doctor
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0VexDoctor.ps1"
set "VEX_DOCTOR_EXIT=%ERRORLEVEL%"
echo.
if "%VEX_DOCTOR_EXIT%"=="0" (
  echo Vex Doctor finished healthy.
) else if "%VEX_DOCTOR_EXIT%"=="1" (
  echo Vex Doctor finished with warnings. Read the report that opened in Notepad.
) else (
  echo Vex Doctor found one or more failures. Read the report that opened in Notepad.
)
echo.
pause
exit /b %VEX_DOCTOR_EXIT%
