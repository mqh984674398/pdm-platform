<#
.SYNOPSIS
  Install or upgrade the Predictive Maintenance Platform on a Windows server (STK-05, T028).

.DESCRIPTION
  Run from the unpacked package folder in an elevated PowerShell:
    powershell -ExecutionPolicy Bypass -File deploy\windows\install.ps1 -Port 8080
  Steps: check Python 3.11/3.12, create backend\.venv, install dependencies (offline from wheelhouse\
  when present), write backend\.env from deploy\pdm.env.example on first install (with a generated
  secret), run database migrations, register a startup task running as SYSTEM, and open the port to the
  local subnet only. Browsers on the LAN then open http://<server>:<port>/ with nothing to install.
  It does not enable production data connections or alerting.
#>
param(
  [int]$Port = 8080,
  [string]$Python = "py",
  [string]$TaskName = "PDM Platform",
  # Load the labeled SIMULATED demo fleet for acceptance (no production data).
  [switch]$SimulatedFleet
)
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$Backend = Join-Path $Root "backend"
$Venv = Join-Path $Backend ".venv"
$Log = Join-Path $Root "deploy\install.log"
function Step($msg) { $line = "[{0:u}] {1}" -f (Get-Date), $msg; Write-Host $line; Add-Content $Log $line }

Step "Install root: $Root"
$ver = & $Python -3 -c "import sys; print('%d.%d' % sys.version_info[:2])"
if ($ver -notin @("3.11", "3.12")) { throw "Python 3.11 or 3.12 is required (found $ver)" }
Step "Python $ver"

if (-not (Test-Path $Venv)) { & $Python -3 -m venv $Venv; Step "Created $Venv" }
$Py = Join-Path $Venv "Scripts\python.exe"
$Wheels = Join-Path $Root "wheelhouse"
if (Test-Path $Wheels) {
  & $Py -m pip install --no-index --find-links $Wheels -r (Join-Path $Backend "requirements.lock")
} else {
  & $Py -m pip install -r (Join-Path $Backend "requirements.lock")
}
if ($LASTEXITCODE -ne 0) { throw "dependency install failed" }
Step "Dependencies installed"

$EnvFile = Join-Path $Backend ".env"
if (-not (Test-Path $EnvFile)) {
  $bytes = New-Object byte[] 48
  [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
  $secret = [Convert]::ToBase64String($bytes)
  (Get-Content (Join-Path $Root "deploy\pdm.env.example")) -replace '^PDM_SECRET_KEY=$', "PDM_SECRET_KEY=$secret" |
    Set-Content $EnvFile -Encoding UTF8
  icacls $EnvFile /inheritance:r /grant:r "SYSTEM:F" "Administrators:F" | Out-Null
  Step "Wrote $EnvFile (edit PDM_DATABASE_URL, then re-run)"
}

Push-Location $Backend
try {
  & $Py -m alembic upgrade head
  if ($LASTEXITCODE -ne 0) { throw "database migration failed; check PDM_DATABASE_URL in $EnvFile" }
  Step "Database migrated"
} finally { Pop-Location }

$Start = Join-Path $Root "deploy\windows\start_pdm.ps1"
$Action = New-ScheduledTaskAction -Execute "powershell.exe" `
  -Argument ("-NoProfile -ExecutionPolicy Bypass -File `"$Start`" -Port $Port" + $(if ($SimulatedFleet) { " -SimulatedFleet" } else { "" })) -WorkingDirectory $Backend
$Trigger = New-ScheduledTaskTrigger -AtStartup
$Settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
  -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings `
  -User "SYSTEM" -RunLevel Highest -Force | Out-Null
Step "Registered startup task '$TaskName'"

$Rule = "PDM Platform $Port"
if (-not (Get-NetFirewallRule -DisplayName $Rule -ErrorAction SilentlyContinue)) {
  New-NetFirewallRule -DisplayName $Rule -Direction Inbound -Protocol TCP -LocalPort $Port `
    -RemoteAddress LocalSubnet -Action Allow | Out-Null
  Step "Firewall: TCP $Port open to LocalSubnet only"
}

Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds $(if ($SimulatedFleet) { 120 } else { 10 })
try {
  $h = Invoke-RestMethod "http://127.0.0.1:$Port/api/health"
  Step "Health check OK: version $($h.version)"
} catch { Step "Health check failed: $_  (see deploy\server.log)"; exit 1 }
Step "Create the first administrator: $Py ..\deploy\manage_users.py create-admin <user>"
