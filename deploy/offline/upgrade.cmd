@echo off
rem Upgrade an existing installation with the code in this folder. Double-click to run.
rem Keeps the database, accounts, settings (pdm\backend\.env) and the bundled Python.
cd /d "%~dp0"
net session >nul 2>&1
if %errorlevel% neq 0 (
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup\upgrade.ps1" %*
echo.
pause
