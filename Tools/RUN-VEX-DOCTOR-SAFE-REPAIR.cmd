@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0VexDoctor.ps1" -RepairSafe -KeepOpen
