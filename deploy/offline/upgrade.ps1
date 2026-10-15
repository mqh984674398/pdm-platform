<#
  Upgrade an existing offline installation (0.1.4). Code only: it replaces pdm\ (backend, built browser
  client, deploy scripts, SIMULATED data) and the setup scripts. It does NOT touch the bundled Python,
  PostgreSQL or the database contents, pdm\backend\.env (passwords, data source accounts, settings), the
  accounts, the startup task or the firewall rule. The schema is migrated to head (a no-op when this release
  has no new migration). A copy of the old pdm\ and, when pg_dump is found, a database dump are written to
  %ProgramData%\PDM\backup\<time>\ first.
  Run it from the unzipped upgrade folder (double-click upgrade.cmd); the installation is found from the
  "PDM Platform" startup task, or pass -InstallRoot <folder that contains runtime\ and pdm\>.
#>
param(
  [string]$InstallRoot = "",
  [string]$PgBin = "",
  [switch]$NoBrowser
)
$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $PSScriptRoot
$NewPdm = Join-Path $Here "pdm"
$Data = Join-Path $env:ProgramData "PDM"
New-Item -ItemType Directory -Force -Path $Data | Out-Null
$Log = Join-Path $Data "upgrade.log"
function Step($zh, $en) { $l = "[{0:yyyy-MM-dd HH:mm:ss}] {1} / {2}" -f (Get-Date), $zh, $en; Write-Host $l -ForegroundColor Cyan; Add-Content $Log $l -Encoding UTF8 }
function Warn($zh, $en) { $l = "[{0:yyyy-MM-dd HH:mm:ss}] 注意：{1} / WARNING: {2}" -f (Get-Date), $zh, $en; Write-Host $l -ForegroundColor Yellow; Add-Content $Log $l -Encoding UTF8 }
function Fail($zh, $en) { Step "失败：$zh" "FAILED: $en"; throw $en }
function Invoke-Native([scriptblock]$Cmd) { $ErrorActionPreference = "Continue"; & $Cmd }
function VersionOf($file) {
  if (-not (Test-Path $file)) { return "?" }
  $m = Select-String -Path $file -Pattern '__version__\s*=\s*"([^"]+)"' | Select-Object -First 1
  if ($m) { return $m.Matches[0].Groups[1].Value } else { return "?" }
}

if (-not (Test-Path (Join-Path $NewPdm "backend\app\__init__.py"))) { Fail "升级包不完整：缺少 pdm\backend" "upgrade package incomplete: pdm\backend is missing" }

# --- 1. Find the installation ---------------------------------------------------------------------------
$TaskName = "PDM Platform"
if (-not $InstallRoot) {
  $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
  if ($task) {
    $exe = ($task.Actions | Select-Object -First 1).Execute -replace '"', ''
    if ($exe) { $InstallRoot = Split-Path -Parent (Split-Path -Parent $exe) }
  }
}
if (-not $InstallRoot) { Fail "找不到已安装的平台，请用 -InstallRoot 指定安装目录" "no installation found; pass -InstallRoot <install folder>" }
$Root = (Resolve-Path $InstallRoot).Path
$Py = Join-Path $Root "runtime\python\python.exe"
$Pdm = Join-Path $Root "pdm"
$Backend = Join-Path $Pdm "backend"
$EnvFile = Join-Path $Backend ".env"
if (-not (Test-Path $Py) -or -not (Test-Path $EnvFile)) { Fail "$Root 不是有效的安装目录（缺少 runtime\python 或 pdm\backend\.env）" "$Root is not an installation (runtime\python or pdm\backend\.env missing)" }
if ((Resolve-Path $Here).Path -eq $Root) { Fail "请在解压出来的升级包文件夹里运行，不要在安装目录里运行" "run this from the unzipped upgrade folder, not from the install folder" }
$OldVer = VersionOf (Join-Path $Backend "app\__init__.py")
$NewVer = VersionOf (Join-Path $NewPdm "backend\app\__init__.py")
Step "安装目录 $Root，版本 $OldVer -> $NewVer" "Install root $Root, version $OldVer -> $NewVer"

# The upgrade carries code only: it must run on the Python packages that are already installed.
$oldLock = Join-Path $Backend "requirements.lock"; $newLock = Join-Path $NewPdm "backend\requirements.lock"
if ((Test-Path $oldLock) -and (Test-Path $newLock)) {
  $a = (Get-Content $oldLock -Raw) -replace "`r`n", "`n"; $b = (Get-Content $newLock -Raw) -replace "`r`n", "`n"
  if ($a -ne $b) { Fail "依赖版本有变化，本升级包只含程序代码，请改用完整安装包" "dependencies changed; this upgrade carries code only, use the full offline package" }
}
Invoke-Native { & $Py -c "import fastapi, sqlalchemy, psycopg, xgboost, sklearn, uvicorn, alembic, httpx" 2>&1 } | Out-Null
if ($LASTEXITCODE -ne 0) { Fail "内置 Python 依赖不完整" "bundled packages failed to import" }

$Port = 8080
$runner = Join-Path $Root "setup\run_server.cmd"
if (Test-Path $runner) {
  $m = Select-String -Path $runner -Pattern '--port\s+(\d+)' | Select-Object -First 1
  if ($m) { $Port = [int]$m.Matches[0].Groups[1].Value }
}

# --- 2. Stop the service, back up -----------------------------------------------------------------------
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupDir = Join-Path $Data "backup\$stamp"
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
icacls $BackupDir /inheritance:r /grant:r "SYSTEM:(OI)(CI)F" "Administrators:(OI)(CI)F" | Out-Null   # the dump holds account hashes
Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Start-Sleep 3
Step "服务已停止" "Service stopped"

$line = Get-Content $EnvFile -Encoding UTF8 | Where-Object { $_ -like "PDM_DATABASE_URL=*" } | Select-Object -First 1
if ($line -match '^PDM_DATABASE_URL=[^:]+://([^:]+):([^@]*)@([^:/]+):(\d+)/(\w+)') {
  $dbUser, $dbPass, $dbHost, $dbPort, $dbName = $Matches[1], $Matches[2], $Matches[3], $Matches[4], $Matches[5]
  if (-not $PgBin) {
    $PgBin = @("$env:ProgramFiles\PostgreSQL\17\bin") | Where-Object { Test-Path (Join-Path $_ "pg_dump.exe") } | Select-Object -First 1
  }
  if ($PgBin -and (Test-Path (Join-Path $PgBin "pg_dump.exe"))) {
    $dump = Join-Path $BackupDir "pdm-database.dump"
    $env:PGPASSWORD = $dbPass
    Invoke-Native { & (Join-Path $PgBin "pg_dump.exe") -h $dbHost -p $dbPort -U $dbUser -Fc -f $dump $dbName 2>&1 } | ForEach-Object { "$_" } | Add-Content $Log -Encoding UTF8
    $dumpCode = $LASTEXITCODE
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    if ($dumpCode -eq 0 -and (Test-Path $dump)) { Step "数据库已备份：$dump" "Database dump written: $dump" }
    else { Warn "数据库备份失败（不影响升级，本次不改动数据库内容）" "database dump failed (the upgrade does not change database contents)" }
  } else { Warn "未找到 pg_dump，跳过数据库备份（可用 -PgBin 指定）" "pg_dump not found, database dump skipped (use -PgBin)" }
} else { Warn "无法从 .env 读取数据库地址，跳过数据库备份" "could not read the database URL from .env, database dump skipped" }

$oldCopy = Join-Path $BackupDir "pdm-before-$OldVer"
Invoke-Native { & robocopy $Pdm $oldCopy /E /XF .env /NFL /NDL /NJH /NJS /NP } | Out-Null   # .env stays where it is
if ($LASTEXITCODE -ge 8) { Fail "备份旧程序失败（robocopy $LASTEXITCODE），未做任何改动" "backing up the old program failed (robocopy $LASTEXITCODE); nothing was changed" }
Step "旧程序已备份：$oldCopy" "Old program folder saved in $oldCopy"

# --- 3. Replace the code --------------------------------------------------------------------------------
$dist = Join-Path $Pdm "frontend\dist"
if (Test-Path $dist) { Remove-Item $dist -Recurse -Force }   # hashed asset names: no stale files
Invoke-Native { & robocopy $NewPdm $Pdm /E /XF .env /NFL /NDL /NJH /NJS /NP } | Out-Null
if ($LASTEXITCODE -ge 8) { Fail "复制程序文件失败（robocopy $LASTEXITCODE）。旧程序备份在 $BackupDir" "copying program files failed (robocopy $LASTEXITCODE); old copy in $BackupDir" }
New-Item -ItemType Directory -Force -Path (Join-Path $Root "setup") | Out-Null
Get-ChildItem (Join-Path $Here "setup") -Filter *.ps1 | ForEach-Object { Copy-Item $_.FullName (Join-Path $Root "setup") -Force }
foreach ($f in "install.cmd", "uninstall.cmd", "verify.cmd", "upgrade.cmd", "DEPLOY_GUIDE.md") {
  if (Test-Path (Join-Path $Here $f)) { Copy-Item (Join-Path $Here $f) $Root -Force }
}
Step "程序文件已更新（.env、数据库、账号未改动）" "Program files replaced (.env, database and accounts untouched)"

# --- 4. Migrate, start ----------------------------------------------------------------------------------
Push-Location $Backend
try {
  Invoke-Native { & $Py -m alembic upgrade head 2>&1 } | ForEach-Object { "$_" } | Add-Content $Log -Encoding UTF8
  if ($LASTEXITCODE -ne 0) { Fail "数据库迁移失败，详见 $Log；可用 $BackupDir 恢复旧程序" "migration failed, see $Log; the old program is in $BackupDir" }
  Step "数据库结构已是最新" "Database schema is at head"
} finally { Pop-Location }

Start-ScheduledTask -TaskName $TaskName
$ok = $false; $h = $null
for ($i = 0; $i -lt 60; $i++) {
  try { $h = Invoke-RestMethod "http://127.0.0.1:$Port/api/health" -TimeoutSec 3; $ok = $true; break } catch { Start-Sleep 2 }
}
if (-not $ok) {
  $ServerLog = Join-Path $Data "server.log"
  if (Test-Path $ServerLog) { Get-Content $ServerLog -Tail 30 }
  Fail "服务未启动，详见 $ServerLog。要回退：把 $oldCopy 里的文件复制回 $Pdm（删除 frontend\dist 后）并重启任务 '$TaskName'" "server did not start; to roll back copy $oldCopy back over $Pdm (delete frontend\dist first) and restart the task '$TaskName'"
}
Step "升级完成：版本 $($h.version)，http://127.0.0.1:$Port/" "Upgrade done: version $($h.version), http://127.0.0.1:$Port/"
if (-not $NoBrowser) { Start-Process "http://127.0.0.1:$Port/" }
