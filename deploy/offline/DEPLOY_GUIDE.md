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
- **仿真数据库仅管理员可用**；工程师、维护、查看角色在配置工作台只能看到涛思数据库。
  **The simulation database is for administrators only**; other roles see only TDengine sources in the Configuration workbench.
- 默认使用 HTTP。如有证书和 HTTPS 反向代理，在 `.env` 中设置 `PDM_COOKIE_SECURE=true`。
  Plain HTTP by default; behind HTTPS set `PDM_COOKIE_SECURE=true`.
- 本地 LLM：如需使用，在本机或局域网安装 Ollama 并只监听 127.0.0.1，然后由管理员在“本地助手”页面配置。
  Local LLM: install Ollama on the server or LAN, bind it to 127.0.0.1, and configure it as an admin in the Local assistant screen.

## 6a. 连接涛思数据库 / Connect TDengine

平台通过 taosAdapter 的 REST 接口（默认端口 6041）读取涛思数据库，无需在服务器上安装 TDengine 客户端。
The platform reads TDengine through taosAdapter's REST endpoint (port 6041); no TDengine client is needed on the server.

**端口与字段 / Port and fields (D-049)**：端口填 taosAdapter 的 REST 端口，默认 **6041**；**6060 是 taosExplorer 网页管理界面**，用浏览器能打开网页并不代表平台能连接。主机只填 IP 或主机名（不带 `http://` 和端口）。“设备标签列”填列名（如 `device_id`），不是某台设备的编号；保存后点“读取表结构”可直接从数据库里选择。数据源在“数据源”页配置，配置工作台只选择。
Use the taosAdapter REST port, default **6041**; **6060 is the taosExplorer web console**, so being able to open the web page does not mean the platform can connect. The host is an IP or host name only (no `http://`, no port). The device tag field takes a column name (such as `device_id`), not a device id; after saving, "Read structure" lets you pick from the database. Sources are set up on the Data sources screen; the Configuration workbench only picks one.

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
4. 在任务计划程序中重启 “PDM Platform”。然后以管理员登录，在“配置工作台”顶部的“数据源”中点击该数据源的“测试连接”，“账号只读”检查必须通过。
   Restart "PDM Platform", sign in as administrator and run "Test connection" for the source under Data sources at the top of the Configuration workbench; the read-only check must pass.

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

## 数据源管理与预测配置版本 / Data source management and configuration versions (D-044)

- 管理员在“配置工作台”顶部的“数据源”中新增、修改、测试、删除涛思数据源；账号密码只写入 `backend\.env`（仅 SYSTEM 与管理员可读），不会返回或存入数据库。测试通过后自动登记标准只读查询模板。
- Administrators add, edit, test and delete TDengine sources under Data sources at the top of the Configuration workbench. The account goes only into `backend\.env` (SYSTEM and Administrators), never to the database or back out through the API. A passing test also registers the standard read-only query templates.
- 旧的“算法配置”页已删除；它的功能由“配置工作台”承担（设备结构、数据源与信号映射、部件预测配置、健康参考与特征生成）。
- The former "Algorithm configuration" page is removed; the Configuration workbench replaces it (plant structure, data sources and signal mappings, per-component prediction configuration, healthy reference and feature building).
- 预测配置版本（草稿→校验→发布→启用）在工作台中操作；启用后决策引擎使用该版本。
- Prediction configuration versions (draft → validate → publish → activate) are handled in the workbench; once active, the decision engine uses the version.
- **一键测试**：安装包根目录的 `verify.cmd`（源码为 `tools\run_demo.cmd`）用内置 Python 在仿真数据上启动一个独立的演示服务（默认 8765 端口，不影响已安装的服务和 PostgreSQL），先自动走完“新部件→信号映射→特征→健康参考→预测配置→启用”共 10 步并逐步显示通过/失败，然后保持服务以便在浏览器手动测试（管理员 `admin`，密码见窗口输出）。加参数 `-Check` 只做检查。尚未在真实 Windows 上运行过。
- **One-click test**: `verify.cmd` in the package root (source: `tools\run_demo.cmd`) starts a separate demo server on SIMULATED data with the bundled Python (port 8765 by default; the installed service and PostgreSQL are untouched), first walks a new component through 10 steps (signals → features → healthy reference → prediction configuration → activate) printing PASS/FAIL per step, then keeps the server up for manual browser testing (administrator `admin`, password shown in the window). Add `-Check` to run the check only. Not yet run on a real Windows machine.

## 升级包 / Upgrade package (0.1.4)

升级包 `pdm-0.1.4-upgrade-win64.zip` 只含程序代码（后端、浏览器前端、部署脚本、模拟示例数据），不含 Python 和 PostgreSQL，所以很小。 The upgrade package carries code only (backend, browser client, deploy scripts, SIMULATED data), no Python or PostgreSQL, so it is small.

1. 解压到任意文件夹（例如桌面），**不要**解压进安装目录。 Unzip into any folder (for example the desktop), **not** into the install folder.
2. 双击 `upgrade.cmd`（会请求管理员权限）。它从“PDM Platform”开机任务找到安装目录；找不到时在 PowerShell 中运行 `setup\upgrade.ps1 -InstallRoot C:\PDM\pdm-offline`。 Double-click `upgrade.cmd`; it finds the installation from the "PDM Platform" startup task, otherwise run `setup\upgrade.ps1 -InstallRoot <install folder>` in PowerShell.
3. 脚本依次：停止服务 → 备份旧程序（`C:\ProgramData\PDM\backup\<时间>\`，不含 `.env`），能找到 `pg_dump` 时同时备份数据库 → 只替换 `pdm\` 下的程序文件 → 迁移数据库结构到最新（无新迁移时不做任何改动）→ 启动服务并检查健康。 It stops the service, backs up the old program (without `.env`) and, when `pg_dump` is found, the database, replaces only program files, migrates to head, starts the service and checks health.
4. 不会改动：数据库内容、账号、`pdm\backend\.env`（含涛思账号）、内置 Python、开机任务、防火墙。 Never touched: database contents, accounts, `pdm\backend\.env` (including TDengine accounts), the bundled Python, the startup task, the firewall rule.
5. 若依赖版本变化（`requirements.lock` 不同），脚本会拒绝并要求使用完整安装包。 If the dependency lock differs, the script refuses and asks for the full package.
6. 回退：服务起不来时，把备份里 `pdm-before-<旧版本>` 的内容复制回 `pdm\`（先删除 `pdm\frontend\dist`），重启任务。 Rollback: copy the backed-up `pdm-before-<old version>` folder back over `pdm\` (delete `pdm\frontend\dist` first) and restart the task.

升级脚本尚未在真实 Windows 上运行过；首次升级前请确认已有你自己的数据库备份。 The upgrade script has not been run on real Windows yet; keep your own database backup before the first upgrade.

## 涛思数据源的采集策略 / How the platform collects from a TDengine source (D-052)

- **只读、拉取式**：平台不写涛思库，也不订阅；服务内的在线流水线每 `PDM_PIPELINE_INTERVAL_MIN` 分钟（默认 15，0 = 关闭）为每台非仿真设备运行一次，也可在“预测前提检查”里点“从数据源生成”手动运行。 Read-only and pull-based: the online pipeline runs every `PDM_PIPELINE_INTERVAL_MIN` minutes (default 15; 0 = off) for each non-simulated machine, or on demand from the prerequisite check.
- **读什么**：只读已映射到该设备部件的信号。每条查询形如 `SELECT ts, value FROM 超级表 WHERE 设备标签=… AND 信号键=… AND ts >= … AND ts < … ORDER BY ts LIMIT n`，受数据源的“最大行数”和“最大时间跨度”限制。 It reads only the signals mapped to the machine's components, one bounded query per signal and window.
- **读多少**：先用安装日期起 4 天的数据学习工况目录（不足 4 天、但已有至少 1 天数据时可临时生成）；之后从“已存特征窗口的末尾”起按每次最多 24 小时、一次运行最多 31 步向前读，只处理已结束的观察窗口，未结束的留到下一次。长时间跨度或行数超限时自动拆成更小的查询（0.1.4 起），单个信号超过 500 万行才会拒绝并说明。 It first learns the regime catalog from the 4 days after installation, then reads forward from the newest stored feature window in steps of up to 24 h (at most 31 steps a run) and only processes windows that have closed. A window that is longer than the source's range limit or fills its row limit is split into smaller queries (from 0.1.4).
- **存什么**：只保存特征窗口和告警，不复制原始数据；再次运行没有新数据时不产生变化。 It stores feature windows and alarms only, never a copy of the raw data.
- **出错时**：读取失败不再让按钮“无反应”，页面会显示数据源返回的原因（0.1.4 起）；定时运行中某台设备出错只记日志，不影响其他设备。 A read failure is shown on the page with the reason from the source; in the scheduled run one machine's failure is only logged.
- **需要你确认的两点**：①服务器返回的时间戳若不带时区（旧版 taosAdapter），请在数据源里把“无时区时间戳的时区”设为服务器所在时区（如 `Asia/Shanghai`），默认的 UTC 会让时间整体偏移；②迟到的数据（时间早于已处理位置才写入涛思库）不会被补读。 Two things to check: a source that returns timestamps without an offset needs its time zone set (default UTC would shift all times); data written late with an old timestamp is not read again.
