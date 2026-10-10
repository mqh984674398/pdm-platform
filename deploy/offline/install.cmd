@echo off
rem One-click offline install of the Predictive Maintenance Platform. Double-click to run.
rem Asks for administrator rights, then runs setup\offline_install.ps1.
cd /d "%~dp0"
net session >nul 2>&1
if %errorlevel% neq 0 (
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup\offline_install.ps1" %*
echo.
pause
