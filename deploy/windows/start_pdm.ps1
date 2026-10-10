# Started by the "PDM Platform" scheduled task; serves the API and browser client on one port.
param([int]$Port = 8080, [switch]$SimulatedFleet)
$Backend = Resolve-Path (Join-Path $PSScriptRoot "..\..\backend")
Set-Location $Backend
$extra = @()
if ($SimulatedFleet) { $extra += "--simulated-fleet" }
& (Join-Path $Backend ".venv\Scripts\python.exe") "..\deploy\serve.py" --port $Port @extra `
  *>> (Join-Path $Backend "..\deploy\server.log")
