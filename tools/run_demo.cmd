@echo off
rem One-click test run on the SIMULATED demo data. Options: -Check (run the flow check and stop), -NoBrowser, -Port n
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_demo.ps1" %*
if errorlevel 1 pause
