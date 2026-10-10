# Removes the startup task and firewall rule. Keeps the database, backend\.env and logs.
param([int]$Port = 8080, [string]$TaskName = "PDM Platform")
Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Remove-NetFirewallRule -DisplayName "PDM Platform $Port" -ErrorAction SilentlyContinue
Write-Host "Removed task '$TaskName' and firewall rule for port $Port. Data and settings were kept."
