<#
  Offline one-click install (T028 follow-up). Uses the bundled Python 3.12 runtime (all packages
  pre-installed) and the PostgreSQL 17 already installed on this machine. No internet needed.
  Steps: locate PostgreSQL 17 -> make sure a server is running (initialise a new cluster as a Windows
  service if none is configured) -> create login "pdm" and database "pdm" -> write pdm\backend\.env ->
  migrate the schema -> create the first administrator -> register a startup task -> open the port to the
  local subnet -> start and check health -> open the browser.
  Production data connections and official alerting stay disabled (G4, D-031).
#>
param(
  [int]$Port = 8080,
  [int]$PgPort = 0,
  [string]$PgBin = "",
  [switch]$SimulatedFleet,
  [switch]$NoBrowser
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Py = Join-Path $Root "runtime\python\python.exe"
$Backend = Join-Path $Root "pdm\backend"
$Data = Join-Path $env:ProgramData "PDM"
New-Item -ItemType Directory -Force -Path $Data | Out-Null
$Log = Join-Path $Data "install.log"
function Step($zh, $en) { $l = "[{0:yyyy-MM-dd HH:mm:ss}] {1} / {2}" -f (Get-Date), $zh, $en; Write-Host $l -ForegroundColor Cyan; Add-Content $Log $l -Encoding UTF8 }
function Fail($zh, $en) { Step "失败：$zh" "FAILED: $en"; throw $en }
# Windows PowerShell 5.1 turns every stderr line of a native command into a terminating error when
# $ErrorActionPreference is Stop and stderr is redirected (alembic logs INFO to stderr, psql reports a
# server that is still starting there). Native tools run with Continue; callers check $LASTEXITCODE.
function Invoke-Native([scriptblock]$Cmd) { $ErrorActionPreference = "Continue"; & $Cmd }
function NewSecret([int]$n) { $b = New-Object byte[] $n; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b); ([Convert]::ToBase64String($b) -replace '[+/=]', 'x') }

Step "安装目录 $Root" "Install root $Root"
if (-not (Test-Path $Py)) { Fail "找不到内置 Python" "bundled Python missing at $Py" }
Invoke-Native { & $Py -c "import fastapi, sqlalchemy, psycopg, xgboost, sklearn, uvicorn, alembic, httpx" 2>&1 } | Out-Null
if ($LASTEXITCODE -ne 0) { Fail "内置 Python 依赖不完整" "bundled packages failed to import" }
Step "内置 Python 3.12 与依赖可用" "Bundled Python 3.12 and packages OK"

# --- 1. PostgreSQL 17 -------------------------------------------------------------------------------
if (-not $PgBin) {
  $cands = @("$env:ProgramFiles\PostgreSQL\17\bin")
  $reg = Get-ItemProperty "HKLM:\SOFTWARE\PostgreSQL\Installations\*" -ErrorAction SilentlyContinue |
    Where-Object { $_.Version -like "17*" }
  foreach ($r in $reg) { $cands = @((Join-Path $r."Base Directory" "bin")) + $cands }
  $PgBin = $cands | Where-Object { Test-Path (Join-Path $_ "psql.exe") } | Select-Object -First 1
}
if (-not $PgBin) { Fail "未找到 PostgreSQL 17，请用 -PgBin 指定 bin 目录" "PostgreSQL 17 not found; pass -PgBin <dir>" }
$ver = & (Join-Path $PgBin "postgres.exe") --version
if ($ver -notmatch " 17\.") { Fail "需要 PostgreSQL 17，找到 $ver" "PostgreSQL 17 required, found $ver" }
Step "找到 $ver ($PgBin)" "Found $ver"
$psql = Join-Path $PgBin "psql.exe"

$svc = Get-Service | Where-Object { $_.Name -like "postgresql*17*" -or $_.Name -eq "pdm-postgresql17" } | Select-Object -First 1
$SuperUser = "postgres"
if ($svc) {
  if ($svc.Status -ne "Running") { Start-Service $svc.Name; Step "已启动服务 $($svc.Name)" "Started service $($svc.Name)" }
  if (-not $PgPort) {
    $conf = (Get-CimInstance Win32_Service -Filter "Name='$($svc.Name)'").PathName
    $dataDir = if ($conf -match '-D\s+"([^"]+)"') { $Matches[1] } else { "" }
    $PgPort = 5432
    if ($dataDir -and (Test-Path "$dataDir\postgresql.conf")) {
      $m = Select-String -Path "$dataDir\postgresql.conf" -Pattern '^\s*port\s*=\s*(\d+)' | Select-Object -First 1
      if ($m) { $PgPort = [int]$m.Matches[0].Groups[1].Value }
    }
  }
  Step "使用已有 PostgreSQL 服务 $($svc.Name)，端口 $PgPort" "Using existing service $($svc.Name), port $PgPort"
  $sec = Read-Host -AsSecureString "请输入 PostgreSQL 超级用户 postgres 的密码 / Password of PostgreSQL superuser 'postgres'"
  $env:PGPASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
} else {
  # Installed but never configured: create a cluster owned by this platform and run it as a service.
  if (-not $PgPort) { $PgPort = 5432 }
  if (Get-NetTCPConnection -LocalPort $PgPort -State Listen -ErrorAction SilentlyContinue) { Fail "端口 $PgPort 已被占用，请用 -PgPort 指定" "port $PgPort is in use; pass -PgPort" }
  $PgData = Join-Path $Data "pgdata17"
  $SuperPass = NewSecret 24
  $pw = Join-Path $Data "pg_super.tmp"; Set-Content $pw $SuperPass -NoNewline -Encoding ASCII
  & (Join-Path $PgBin "initdb.exe") -D $PgData -U postgres --pwfile=$pw -E UTF8 --locale=C -A scram-sha-256 | Out-Null
  Remove-Item $pw
  if ($LASTEXITCODE -ne 0) { Fail "initdb 失败" "initdb failed" }
  Add-Content "$PgData\postgresql.conf" "`nport = $PgPort`nlisten_addresses = '127.0.0.1'`n"
  & (Join-Path $PgBin "pg_ctl.exe") register -N "pdm-postgresql17" -D $PgData -S auto | Out-Null
  icacls $PgData /grant "NT AUTHORITY\NetworkService:(OI)(CI)F" | Out-Null
  Start-Service "pdm-postgresql17"
  $env:PGPASSWORD = $SuperPass
  Set-Content (Join-Path $Data "postgres_superuser.txt") "postgres / $SuperPass" -Encoding ASCII
  icacls (Join-Path $Data "postgres_superuser.txt") /inheritance:r /grant:r "SYSTEM:F" "Administrators:F" | Out-Null
  Step "已初始化 PostgreSQL 17 数据库集群（服务 pdm-postgresql17，仅本机 127.0.0.1:$PgPort）" "Initialised a PostgreSQL 17 cluster as service pdm-postgresql17 on 127.0.0.1:$PgPort"
}

function Sql($db, $q) { Invoke-Native { & $psql -h 127.0.0.1 -p $PgPort -U $SuperUser -d $db -v ON_ERROR_STOP=1 -tAc $q } }
for ($i = 0; $i -lt 30; $i++) { if ((Sql "postgres" "select 1" 2>$null) -eq "1") { break }; Start-Sleep 1 }
if ((Sql "postgres" "select 1" 2>$null) -ne "1") { Fail "无法连接 PostgreSQL（检查密码或端口）" "cannot connect to PostgreSQL (check password/port)" }

$EnvFile = Join-Path $Backend ".env"
$existing = if (Test-Path $EnvFile) { Get-Content $EnvFile -Encoding UTF8 } else { @() }
$dbLine = $existing | Where-Object { $_ -like "PDM_DATABASE_URL=*" }
if (-not $dbLine) {
  $AppPass = NewSecret 24
  if ((Sql "postgres" "select 1 from pg_roles where rolname='pdm'") -eq "1") {
    Sql "postgres" "alter role pdm with login password '$AppPass'" | Out-Null
  } else {
    Sql "postgres" "create role pdm with login password '$AppPass'" | Out-Null
  }
  if ((Sql "postgres" "select 1 from pg_database where datname='pdm'") -ne "1") {
    Sql "postgres" "create database pdm owner pdm encoding 'UTF8' template template0" | Out-Null
  }
  Sql "pdm" "alter schema public owner to pdm" | Out-Null
  $dbLine = "PDM_DATABASE_URL=postgresql+psycopg://pdm:$AppPass@127.0.0.1:$PgPort/pdm"
  Step "已创建数据库 pdm 与登录 pdm" "Created database pdm and login pdm"
}
Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue

# --- 2. Settings --------------------------------------------------------------------------------------
$secret = ($existing | Where-Object { $_ -like "PDM_SECRET_KEY=*" }) ; if (-not $secret) { $secret = "PDM_SECRET_KEY=" + (NewSecret 48) }
# Keep everything already in the file (data source passwords PDM_SECRET_*, a changed pipeline interval, ...):
# only keys that are missing get the default below.
$defaults = [ordered]@{
  PDM_AUTH_MODE = "local"
  PDM_COOKIE_SECURE = "false"
  PDM_STATIC_DIR = "../frontend/dist"
  PDM_DATASOURCES_FILE = "../deploy/datasources.simulated.json"
  PDM_PRODUCTION_DATA_APPROVED = "false"
  PDM_LLM_ENABLED = "false"
}
$lines = @($existing | Where-Object { $_ -and $_ -notlike "PDM_DATABASE_URL=*" -and $_ -notlike "PDM_SECRET_KEY=*" })
foreach ($k in $defaults.Keys) { if (-not ($lines | Where-Object { $_ -like "$k=*" })) { $lines += "$k=$($defaults[$k])" } }
(@($dbLine, $secret) + $lines) | Set-Content $EnvFile -Encoding ASCII
icacls $EnvFile /inheritance:r /grant:r "SYSTEM:F" "Administrators:F" | Out-Null
Step "已写入配置 pdm\backend\.env（仅 SYSTEM 与管理员可读）" "Wrote pdm\backend\.env (SYSTEM and Administrators only)"

# --- 3. Schema and first administrator ----------------------------------------------------------------
Push-Location $Backend
try {
  Invoke-Native { & $Py -m alembic upgrade head 2>&1 } | ForEach-Object { "$_" } | Add-Content $Log -Encoding UTF8
  if ($LASTEXITCODE -ne 0) { Fail "数据库迁移失败，详见 $Log" "migration failed, see $Log" }
  Step "数据库结构已更新" "Database schema migrated"
  $users = & $Py ..\deploy\manage_users.py list
  if (-not ($users -match "admin\s+active")) {
    $admin = Read-Host "创建第一个管理员：用户名 / First administrator user name"
    & $Py ..\deploy\manage_users.py create-admin $admin
    if ($LASTEXITCODE -ne 0) { Fail "创建管理员失败" "creating the administrator failed" }
  }
} finally { Pop-Location }

# --- 4. Startup task, firewall, start -----------------------------------------------------------------
$TaskName = "PDM Platform"
$serveArgs = "..\deploy\serve.py --port $Port" + $(if ($SimulatedFleet) { " --simulated-fleet" } else { "" })
$runner = Join-Path $Root "setup\run_server.cmd"
Set-Content $runner "@echo off`r`ncd /d `"$Backend`"`r`n`"$Py`" $serveArgs >> `"$Data\server.log`" 2>&1`r`n" -Encoding Default
Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
$action = New-ScheduledTaskAction -Execute "`"$runner`"" -WorkingDirectory $Backend
$settings = New-ScheduledTaskSettingsSet -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger (New-ScheduledTaskTrigger -AtStartup) -Settings $settings -User "SYSTEM" -RunLevel Highest -Force | Out-Null
$rule = "PDM Platform $Port"
Remove-NetFirewallRule -DisplayName $rule -ErrorAction SilentlyContinue
New-NetFirewallRule -DisplayName $rule -Direction Inbound -Protocol TCP -LocalPort $Port -RemoteAddress LocalSubnet -Action Allow | Out-Null
Step "已注册开机任务并只对本地子网开放端口 $Port" "Startup task registered; port $Port open to the local subnet only"

Start-ScheduledTask -TaskName $TaskName
$ok = $false
$ServerLog = "$Data\server.log"
for ($i = 0; $i -lt 60; $i++) {
  try { $h = Invoke-RestMethod "http://127.0.0.1:$Port/api/health" -TimeoutSec 3; $ok = $true; break } catch { Start-Sleep 2 }
  if ($i % 5 -eq 4) {
    $state = (Get-ScheduledTask -TaskName $TaskName).State
    $info = Get-ScheduledTaskInfo -TaskName $TaskName
    Step "任务上次结果 $($info.LastTaskResult)，运行时间 $($info.LastRunTime)" "Task last result $($info.LastTaskResult), last run $($info.LastRunTime)"
    Step "等待服务启动… 已 $(($i + 1) * 2) 秒（任务状态：$state）" "Waiting for the service… $(($i + 1) * 2) s (task state: $state)"
    if (Test-Path $ServerLog) { Get-Content $ServerLog -Tail 3 | ForEach-Object { "    $_" } }
  }
}
if (-not $ok) {
  if (Test-Path $ServerLog) { Get-Content $ServerLog -Tail 30 }
  Fail "服务未启动，详见 $ServerLog" "server did not start, see $ServerLog"
}
$ip = (Get-NetIPAddress -AddressFamily IPv4 -PrefixOrigin Dhcp, Manual -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -notlike "169.254*" } | Select-Object -First 1).IPAddress
Step "部署完成：http://${ip}:$Port/  （版本 $($h.version)）" "Done: http://${ip}:$Port/ (version $($h.version))"
if (-not $NoBrowser) { Start-Process "http://127.0.0.1:$Port/" }
