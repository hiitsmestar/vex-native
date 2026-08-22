@echo off
setlocal
cd /d "%~dp0"
echo.
echo Starting VexDoctor safe repair pass...
echo This only starts/restarts known local Vex services and calls the Bridge's bounded repair endpoint.
echo It does not delete personal files or run registry cleaners.
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0VexDoctor.ps1" -RepairSafe
set "VEX_DOCTOR_EXIT=%ERRORLEVEL%"
echo.
if "%VEX_DOCTOR_EXIT%"=="0" (
  echo Safe repair finished and verification found no failures.
) else if "%VEX_DOCTOR_EXIT%"=="1" (
  echo Safe repair finished; verification still has warnings.
) else (
  echo Safe repair finished; verification still has one or more failures.
)
echo.
echo Press any key to close this window.
pause >nul
exit /b %VEX_DOCTOR_EXIT%
