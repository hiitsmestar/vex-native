@echo off
cd /d "%~dp0"
type nul > "%~dp0STOP-VEX-WATCHDOG"
taskkill /IM VexBridge.exe /T /F >nul 2>&1
