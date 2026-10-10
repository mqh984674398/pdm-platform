# Removes the startup task and firewall rule. Keeps the database, settings and logs.
param([int]$Port = 8080)
Stop-ScheduledTask -TaskName "PDM Platform" -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName "PDM Platform" -Confirm:$false -ErrorAction SilentlyContinue
Get-NetFirewallRule -DisplayName "PDM Platform*" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
Write-Host "已停止并移除开机任务和防火墙规则；数据库、配置和日志已保留。/ Task and firewall rule removed; data kept."
