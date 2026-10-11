# 预测性维护平台 · 离线一键部署说明 / Offline one-click deployment guide

版本 Version 0.1.1 · 适用于 Windows 10/11、Windows Server 2019+（64 位）· 服务器**无需联网**

## 1. 安装包内容 / What is in the bundle

| 路径 Path | 内容 Contents |
|---|---|
| `install.cmd` | 双击运行的一键安装入口（自动请求管理员权限）。Double-click installer (asks for administrator rights). |
| `uninstall.cmd` | 停止并移除开机任务和防火墙规则，保留数据。Removes the startup task and firewall rule; keeps data. |
| `setup\` | PowerShell 安装脚本。Installer scripts. |
| `runtime\python\` | 内置 Windows Python 3.12.10，35 个依赖包已预装，不使用系统 Python。Bundled Python 3.12.10 with all 35 packages pre-installed. |
| `pdm\` | 平台程序、数据库迁移、浏览器前端、模拟示例数据。Platform, migrations, browser client, SIMULATED sample data. |

不包含 PostgreSQL：使用本机**已安装的 PostgreSQL 17**。Ollama 为可选组件，不包含。
PostgreSQL is not included: the installer uses the **PostgreSQL 17 already installed** on the server. Ollama is optional and not included.

## 2. PostgreSQL 17 兼容性自检 / PostgreSQL 17 compatibility check

打包前已在 PostgreSQL **17.10** 上验证（2026-10-10）：
Verified on PostgreSQL **17.10** before packaging (2026-10-10):

- 后端完整测试 532 项通过，1 项跳过（需要真实 Ollama）。Full backend suite: 532 passed, 1 skipped (live Ollama).
- 数据库迁移 0001→0010 在 PostgreSQL 17 上全部成功。All migrations 0001→0010 ran on PostgreSQL 17.
- 生产模式部署冒烟测试 26/26 通过（本地登录、PostgreSQL 17、单端口前端、模拟车队写入 1513 个特征窗口）。Production-mode smoke test 26/26 passed.
- 数据库驱动 psycopg 3.3.6 支持 PostgreSQL 17。The psycopg 3.3.6 driver supports PostgreSQL 17.

## 3. 一键安装 / One-click install

1. 把 `pdm-0.1.1-offline-win64.zip` 拷贝到服务器，解压到固定位置，例如 `C:\PDM`（路径不要放在桌面或下载目录，安装后不要移动）。
   Copy the zip to the server and extract it to a permanent folder such as `C:\PDM` (do not move it afterwards).
2. 双击 `C:\PDM\pdm-offline\install.cmd`，在 UAC 提示中选“是”。
   Double-click `install.cmd` and accept the UAC prompt.
3. 按提示操作 / Answer the prompts:
   - **如果 PostgreSQL 17 已作为服务运行**（例如用官方安装程序安装过）：输入安装时设置的 `postgres` 超级用户密码。
     **If PostgreSQL 17 already runs as a service**: enter the `postgres` superuser password chosen at install.
   - **如果只安装了程序、没有初始化数据库**：安装脚本会自动创建数据目录 `C:\ProgramData\PDM\pgdata17`，注册服务 `pdm-postgresql17`（只监听 127.0.0.1），并生成随机超级用户密码保存在 `C:\ProgramData\PDM\postgres_superuser.txt`（仅管理员可读）。
     **If PostgreSQL 17 is installed but never initialised**: the installer creates a cluster in `C:\ProgramData\PDM\pgdata17`, registers service `pdm-postgresql17` (127.0.0.1 only), and stores a random superuser password in `C:\ProgramData\PDM\postgres_superuser.txt` (administrators only).
   - 输入第一个管理员的用户名和密码（至少 10 个字符）。Enter the first administrator's user name and password (10+ characters).
4. 完成后浏览器自动打开平台；局域网内其他电脑访问窗口最后显示的地址，例如 `http://192.168.1.20:8080/`。
   The browser opens when done; other LAN computers use the address shown at the end, e.g. `http://192.168.1.20:8080/`.

安装脚本自动完成：创建数据库 `pdm` 与专用登录 `pdm`（随机密码）、写入配置、迁移数据库结构、注册开机自启任务 “PDM Platform”（以 SYSTEM 运行）、防火墙只对本地子网开放端口、健康检查。
The installer creates database `pdm` with a dedicated login (random password), writes settings, migrates the schema, registers the "PDM Platform" startup task (runs as SYSTEM), opens the port to the local subnet only, and checks health.

### 可选参数 / Options

在管理员 PowerShell 中运行 / From an elevated PowerShell:
```powershell
cd C:\PDM\pdm-offline
powershell -ExecutionPolicy Bypass -File setup\offline_install.ps1 -Port 8080 -PgPort 5432 -PgBin "C:\Program Files\PostgreSQL\17\bin" -SimulatedFleet
```
- `-Port` 平台端口（默认 8080）Platform port.
- `-PgPort` PostgreSQL 端口（默认从服务配置读取）PostgreSQL port.
- `-PgBin` PostgreSQL 17 的 bin 目录（自动查找失败时使用）bin folder if auto-detection fails.
- `-SimulatedFleet` 载入带“模拟”标记的示例车队用于验收 Load the labeled SIMULATED demo fleet for acceptance.

重复运行 `install.cmd` 是安全的：会保留已有数据库密码和会话密钥，只更新程序和数据库结构（升级也用这种方式）。
Re-running `install.cmd` is safe: it keeps the database password and session secret and only updates the program and schema (also the upgrade path).

## 4. 账号管理 / Accounts

```powershell
cd C:\PDM\pdm-offline\pdm\backend
..\..\runtime\python\python.exe ..\deploy\manage_users.py create zhang --role engineer
..\..\runtime\python\python.exe ..\deploy\manage_users.py deactivate zhang
..\..\runtime\python\python.exe ..\deploy\manage_users.py reset-password zhang
..\..\runtime\python\python.exe ..\deploy\manage_users.py list
```
角色 Roles: `viewer` 查看 · `maintenance` 维护 · `engineer` 工程师 · `admin` 管理员。连续 5 次密码错误锁定 5 分钟。5 failed sign-ins lock an account for 5 minutes.

## 5. 日常运维 / Operations

| 操作 Task | 方法 How |
|---|---|
| 停止/启动 Stop/start | 任务计划程序 → “PDM Platform”。Task Scheduler → "PDM Platform". |
| 日志 Logs | `C:\ProgramData\PDM\install.log`、`server.log` |
| 配置 Settings | `pdm\backend\.env`（仅 SYSTEM 与管理员可读）|
| 备份 Backup | `"C:\Program Files\PostgreSQL\17\bin\pg_dump.exe" -h 127.0.0.1 -U pdm -Fc pdm > pdm.dump` |
| 卸载 Uninstall | 双击 `uninstall.cmd`；数据库需手动删除。Double-click `uninstall.cmd`; drop the database manually if wanted. |

## 6. 安全与审批 / Security and approvals

- **涛思数据库（TDengine）无需管理员审批**，但必须使用只读账号（D-035）。其他生产数据库（PostgreSQL 等）仍默认关闭（`PDM_PRODUCTION_DATA_APPROVED=false`）。**没有正式维护告警**，开启需要您另外明确批准。
  **TDengine needs no administrator approval** but must use a read-only account (D-035). Other production databases stay off by default; there is no official alerting.
- **仿真数据库仅管理员可用**；工程师、维护、查看角色在算法配置只能看到涛思数据库。
  **The simulation database is for administrators only**; other roles see only TDengine sources in Algorithm configuration.
- 默认使用 HTTP。如有证书和 HTTPS 反向代理，在 `.env` 中设置 `PDM_COOKIE_SECURE=true`。
  Plain HTTP by default; behind HTTPS set `PDM_COOKIE_SECURE=true`.
- 本地 LLM：如需使用，在本机或局域网安装 Ollama 并只监听 127.0.0.1，然后由管理员在“本地助手”页面配置。
  Local LLM: install Ollama on the server or LAN, bind it to 127.0.0.1, and configure it as an admin in the Local assistant screen.

## 6a. 连接涛思数据库 / Connect TDengine

平台通过 taosAdapter 的 REST 接口（默认端口 6041）读取涛思数据库，无需在服务器上安装 TDengine 客户端。
The platform reads TDengine through taosAdapter's REST endpoint (port 6041); no TDengine client is needed on the server.

1. 在 TDengine 中建立只读账号（示例）/ Create a read-only TDengine user, for example:
   `CREATE USER pdm_reader PASS '...'; GRANT READ ON plant_iot.* TO pdm_reader;`
2. 复制 `pdm\deploy\datasources.tdengine.example.json` 为 `pdm\deploy\datasources.json`，修改 `host`、`port`、`database`，以及 `tdengine_layout` 中的超级表 `stable`、设备标签 `device_tag`、时间列 `time_column`。
   Copy the example to `datasources.json` and set host, port, database and the super table layout.
   - 宽表（每个信号一列，TDengine 常见做法）：`value_columns` 留空表示读取所有数值列，或列出要使用的列。
     Wide tables (one column per signal): leave `value_columns` empty for every numeric column, or list them.
   - 窄表（有信号名列）：设置 `key_column`，并在 `value_columns` 中列出数值列。
     Narrow tables: set `key_column` and list the value columns.
3. 在 `pdm\backend\.env` 中加入账号（格式 `用户名:密码`）并指向新文件：
   Add the account and point to the new file in `.env`:
   ```
   PDM_SECRET_TAOS_READONLY=pdm_reader:密码
   PDM_DATASOURCES_FILE=..\deploy\datasources.json
   ```
4. 在任务计划程序中重启 “PDM Platform”。然后在算法配置第 1 步选择该数据源并点击“测试连接”，“只读”检查必须通过。
   Restart "PDM Platform", then pick the source in Studio step 1 and run the connection test; the read-only check must pass.

注意：平台只发送 SELECT / SHOW / DESCRIBE 语句；只读账号是最终保障。尚未连接真实涛思数据库验证（见第 8 节）。
The platform sends only SELECT / SHOW / DESCRIBE; the read-only account is the final safeguard. Not yet verified against a real TDengine server (see section 8).

## 7. 常见问题 / Troubleshooting

| 现象 Symptom | 处理 Fix |
|---|---|
| 未找到 PostgreSQL 17 / not found | 用 `-PgBin` 指定 bin 目录。Pass `-PgBin`. |
| 无法连接 PostgreSQL / cannot connect | 检查 postgres 密码和端口；确认服务正在运行。Check the password, port and service. |
| 端口被占用 / port in use | 用 `-Port` 或 `-PgPort` 换端口。Use another port. |
| 服务未启动 / server did not start | 查看 `C:\ProgramData\PDM\server.log`。 |
| 其他电脑打不开 / LAN clients cannot connect | 确认在同一子网；检查防火墙规则 “PDM Platform 8080”。Same subnet; check the firewall rule. |

## 8. 验证状态 / Verification status

已验证：PostgreSQL 17.10 兼容性、全部依赖都有 Windows 64 位预编译包且已装入内置 Python、生产模式冒烟测试（Linux）。
**尚未在真实 Windows 机器上运行过 `install.cmd`**（构建环境为 Linux，无法执行 PowerShell）。首次安装时请保留 `C:\ProgramData\PDM\install.log`，有问题发给我。
Verified: PostgreSQL 17.10 compatibility, every dependency present as a Windows 64-bit build in the bundled Python, production-mode smoke test (Linux). **`install.cmd` has not yet run on a real Windows machine** (the build environment is Linux and cannot execute PowerShell). Keep `install.log` from the first install and send it to me if anything fails.

---

## 0.1.2 补充 / 0.1.2 addendum

- **在线特征流水线 / Online feature pipeline**：服务每 `PDM_PIPELINE_INTERVAL_MIN` 分钟（默认 15，`backend\.env` 中设为 0 关闭）为已映射信号的真实设备学习工况、提取特征并同步告警。新设备需先有 4 天以上数据，并由工程师在“基线对比”页确认健康参考，之后才会给出健康结论（此前为“未知”）。
  Every `PDM_PIPELINE_INTERVAL_MIN` minutes (default 15; 0 in `backend\.env` turns it off) the service learns regimes, extracts features and syncs alarms for non-simulated machines with mapped signals. A new machine needs 4+ days of data and an engineer-verified healthy reference on the Baselines screen before it gets a health verdict.
- **扭矩安全规则 / Torque safety rule**：在“设备结构”页为丝杠/直线电机部件填写扭矩限值（与扭矩信号同单位），SF-TORQUE-LIMIT 才会生效；未填写则不评估。
  Set a torque limit (unit of the torque signal) per ball-screw / linear-motor component on the plant screen to enable SF-TORQUE-LIMIT; without it the rule is not evaluated.
- **确认健康参考 / Verifying a reference**：选择确认为健康的时段并写明理由；若时段内已有漂移或窗口少于 10 个会给出提示（不阻止）。
  Pick a period you know is healthy; drift inside it or fewer than 10 windows is flagged (not blocked).
