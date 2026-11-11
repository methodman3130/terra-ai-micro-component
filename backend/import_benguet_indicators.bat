@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\import_benguet_indicators.ps1"
echo.
pause
