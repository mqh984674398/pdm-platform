@echo off
rem Joins the two volumes back into pdm-0.1.0-offline-win64.zip and checks its SHA-256.
cd /d "%~dp0"
copy /b pdm-0.1.0-offline-win64.zip.001+pdm-0.1.0-offline-win64.zip.002 pdm-0.1.0-offline-win64.zip >nul
if errorlevel 1 (
  echo Join failed: put both .001 and .002 next to this file.
  pause
  exit /b 1
)
certutil -hashfile pdm-0.1.0-offline-win64.zip SHA256 | findstr /i "70e5181e99f50df8f68a1f80df1e1769f3874ed117fec3ee60a518a2cf8ecfa3" >nul
if errorlevel 1 (
  echo SHA-256 mismatch: download the volumes again.
) else (
  echo OK: pdm-0.1.0-offline-win64.zip is complete. Unzip it and double-click install.cmd.
)
pause
