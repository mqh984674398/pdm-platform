<#
 One-click test run of the platform on the SIMULATED demo data (Windows PowerShell 5.1+).

   run_demo.cmd             start the demo, run the end-to-end flow check, keep it running for the browser
   run_demo.cmd -Check      start, run the flow check, stop (exit code 0 only if every step passed)

 Works from the offline package (uses its bundled Python in runtime\python) and from a source checkout
 (backend\.venv, or any Python 3.11/3.12 on PATH with backend\requirements.lock installed).
 The demo uses a fresh SQLite database under %TEMP%\pdm-demo; it never touches PostgreSQL or the
 installed service, and listens on its own port (default 8765).
 Browser: http://127.0.0.1:<Port>   accounts: admin / engineer   password: see below
#>
param(
  [int]$Port = 8765,
  [string]$Password = "demo-pdm-2026",
  [switch]$Check,
  [switch]$NoBrowser
)
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root   # relative paths below keep non-ASCII install folders out of the command lines

function Say($m) { Write-Host ""; Write-Host "== $m" }

Say "Python"
$candidates = @("runtime\python\python.exe", "..\runtime\python\python.exe", "backend\.venv\Scripts\python.exe")
$Py = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Py) {
  $cmd = Get-Command python -ErrorAction SilentlyContinue
  if (-not $cmd) { Write-Host "No Python found (expected runtime\python in the offline package, or Python 3.12 on PATH)."; exit 1 }
  $Py = $cmd.Source
}
& $Py --version
& $Py -c "import fastapi, sqlalchemy, alembic, uvicorn" 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host "Backend dependencies are missing in $Py."
  Write-Host "Source checkout: $Py -m pip install -r backend\requirements.lock ; $Py -m pip install --no-deps .\backend"
  exit 1
}

Say "Browser client"
if (-not (Test-Path "frontend\dist\index.html")) {
  if (Get-Command npm -ErrorAction SilentlyContinue) {
    Push-Location frontend; npm ci --no-audit --no-fund; npm run build; Pop-Location
  }
}
if (-not (Test-Path "frontend\dist\index.html")) { Write-Host "frontend\dist is missing and could not be built (Node 20+ needed)."; exit 1 }
Write-Host "frontend\dist ready"

Say "Starting the demo server on port $Port (simulated data; building the demo fleet takes a minute)"
$work = Join-Path $env:TEMP "pdm-demo"
New-Item -ItemType Directory -Force -Path $work | Out-Null
$log = Join-Path $work "server.log"; $err = Join-Path $work "server.err.log"
$serverArgs = @("backend\scripts\demo_server.py", "--db", (Join-Path $work "demo.db"), "--port", "$Port",
  "--host", "0.0.0.0", "--static", "frontend\dist", "--local-auth", $Password)
$server = Start-Process -FilePath $Py -ArgumentList $serverArgs -WorkingDirectory $Root -PassThru -WindowStyle Hidden `
  -RedirectStandardOutput $log -RedirectStandardError $err
$up = $false
for ($i = 0; $i -lt 120 -and -not $up; $i++) {
  Start-Sleep -Seconds 3
  if ($server.HasExited) { Write-Host "Server exited; log:"; Get-Content $err -Tail 30; exit 1 }
  try { $up = (Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$Port/api/health" -TimeoutSec 5).StatusCode -eq 200 } catch { }
}
if (-not $up) { Write-Host "Server did not come up; log:"; Get-Content $err -Tail 30; Stop-Process -Id $server.Id -Force; exit 1 }

Say "Flow check: one new component from plant tree to active prediction configuration"
& $Py tools\verify_workflow.py --base "http://127.0.0.1:$Port" --password $Password
$code = $LASTEXITCODE

if ($Check -or $code -ne 0) {
  Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
  if ($code -ne 0) { Write-Host "FLOW CHECK FAILED (exit $code). Server log: $log"; exit $code }
  exit 0
}

Say "Ready for manual testing"
Write-Host "Open   http://127.0.0.1:$Port   (SIMULATED data)"
Write-Host "Sign in as admin or engineer, password: $Password"
Write-Host "Configuration workbench: Administration > Configuration workbench"
if (-not $NoBrowser) { Start-Process "http://127.0.0.1:$Port" }
Read-Host "Press Enter to stop the demo server"
Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
