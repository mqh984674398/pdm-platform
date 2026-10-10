# 部署说明 · Deployment guide (Windows / LAN)

## 中文

**适用范围**：一台 Windows 服务器（Windows Server 2019+ 或 Windows 10/11），局域网内的浏览器直接访问，客户端无需安装任何软件。

### 前置条件
1. Python 3.12（或 3.11），安装时勾选 “py launcher”。
2. PostgreSQL 14+，为本平台创建数据库和账号（例如 `pdm`）。这是平台自己的应用数据库，**不是**生产 IoT 数据库。
3. 可选：Ollama（仅本机或局域网）。请让 Ollama 只监听 `127.0.0.1`，或用防火墙限制只允许本服务器访问。

### 安装
1. 解压 `pdm-<版本>-windows.zip`，例如到 `C:\pdm`。
2. 以管理员身份打开 PowerShell：
   ```powershell
   cd C:\pdm\pdm
   powershell -ExecutionPolicy Bypass -File deploy\windows\install.ps1 -Port 8080
   ```
   第一次运行会生成 `backend\.env`（含随机会话密钥）并提示修改 `PDM_DATABASE_URL`；修改后再次运行。
   需要用模拟示例数据验收时加 `-SimulatedFleet`（所有数据均标记为“模拟”）。
3. 创建第一个管理员：
   ```powershell
   cd C:\pdm\pdm\backend
   .venv\Scripts\python.exe ..\deploy\manage_users.py create-admin admin
   ```
4. 局域网内浏览器打开 `http://<服务器名或IP>:8080/`，用账号登录。为其他人创建账号：`manage_users.py create <用户名> --role viewer|maintenance|engineer|admin`；停用：`manage_users.py deactivate <用户名>`（管理员也可调用 `/api/auth/users` 接口）。

### 离线服务器
在可上网的打包机器上运行 `python deploy/build_package.py --wheelhouse`，压缩包会包含 `wheelhouse\`，安装脚本自动离线安装依赖。

### 安全默认值
- 登录方式为本地账号（`PDM_AUTH_MODE=local`），会话 Cookie 为 HttpOnly / SameSite=Strict；连续 5 次密码错误锁定 5 分钟。
- 防火墙规则只对本地子网开放端口。如果有 HTTPS 反向代理，设置 `PDM_COOKIE_SECURE=true`。
- **生产数据连接默认关闭**：`PDM_PRODUCTION_DATA_APPROVED=false` 时，配置文件中的非模拟数据源会被跳过。只有在用户明确批准（G4）后才能改为 `true`。
- **正式维护告警不存在**：报警仅作为平台内的复核记录，不会发送任何通知。

### 升级、停止、卸载
- 升级：解压新版本覆盖程序文件（保留 `backend\.env`），再运行一次 `install.ps1`（会自动迁移数据库）。
- 停止/启动：任务计划程序中的 “PDM Platform” 任务。
- 卸载：`deploy\windows\uninstall.ps1`（保留数据库、配置和日志）。
- 日志：`deploy\install.log`、`deploy\server.log`。

## English

**Scope**: one Windows server (Windows Server 2019+ or Windows 10/11); browsers on the LAN connect directly with nothing to install.

### Prerequisites
1. Python 3.12 (or 3.11) with the "py launcher".
2. PostgreSQL 14+ with a database and login for the platform (e.g. `pdm`). This is the platform's own application database, **not** the production IoT database.
3. Optional: Ollama on this server or the LAN. Bind it to `127.0.0.1` or firewall it to this server.

### Install
1. Unzip `pdm-<version>-windows.zip`, e.g. to `C:\pdm`.
2. In an elevated PowerShell:
   ```powershell
   cd C:\pdm\pdm
   powershell -ExecutionPolicy Bypass -File deploy\windows\install.ps1 -Port 8080
   ```
   The first run writes `backend\.env` (with a random session secret) and asks you to set `PDM_DATABASE_URL`; run it again afterwards. Add `-SimulatedFleet` to load the labeled SIMULATED demo fleet for acceptance.
3. Create the first administrator:
   ```powershell
   cd C:\pdm\pdm\backend
   .venv\Scripts\python.exe ..\deploy\manage_users.py create-admin admin
   ```
4. Open `http://<server>:8080/` from any LAN browser, and sign in. Create accounts for others with `manage_users.py create <user> --role viewer|maintenance|engineer|admin` and deactivate them with `manage_users.py deactivate <user>` (admins can also use the `/api/auth/users` API).

### Offline servers
Run `python deploy/build_package.py --wheelhouse` on a build machine with internet; the zip then carries `wheelhouse\` and the installer uses it.

### Security defaults
- Local accounts (`PDM_AUTH_MODE=local`), HttpOnly / SameSite=Strict session cookie, 5 failed sign-ins lock an account for 5 minutes.
- The firewall rule admits the local subnet only. Behind an HTTPS reverse proxy set `PDM_COOKIE_SECURE=true`.
- **Production data connections are off**: with `PDM_PRODUCTION_DATA_APPROVED=false` non-simulated sources in the data-source file are skipped. Change it only after the user's explicit approval (G4).
- **There is no official maintenance alerting**: alarms are review records inside the platform and send no notifications.

### Upgrade, stop, uninstall
- Upgrade: unzip the new version over the program files (keep `backend\.env`) and run `install.ps1` again (it migrates the database).
- Stop/start: the "PDM Platform" task in Task Scheduler.
- Uninstall: `deploy\windows\uninstall.ps1` (keeps the database, settings and logs).
- Logs: `deploy\install.log`, `deploy\server.log`.

## Verification status

The package was unpacked and run in production mode on Linux with PostgreSQL (`contracts/evidence/T028/deployment_log.txt`, 26 checks passed). **`install.ps1` has not been run on Windows yet**; the first Windows install is the remaining deployment check.
