@echo off
setlocal
cd /d "%~dp0"
echo.
echo Starting VexDoctor diagnostics...
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0VexDoctor.ps1"
set "VEX_DOCTOR_EXIT=%ERRORLEVEL%"
echo.
if "%VEX_DOCTOR_EXIT%"=="0" (
  echo Diagnostic finished with no failures.
) else if "%VEX_DOCTOR_EXIT%"=="1" (
  echo Diagnostic finished with warnings.
) else (
  echo Diagnostic found one or more failures.
)
echo.
echo Press any key to close this window.
pause >nul
exit /b %VEX_DOCTOR_EXIT%
