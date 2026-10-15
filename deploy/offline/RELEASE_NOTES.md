## 0.1.5（2026-10-15）

升级包（只含程序代码，不改数据库内容、账号与 `.env`；数据库结构自动迁移到 0016）/ Upgrade package (code only; database contents, accounts and `.env` untouched; schema migrates to 0017). 包含 0.1.4 之后的全部修复 / Includes everything fixed after 0.1.4:
- 新增：设备总览按车间分页；管理员长按设备 0.5 秒后可拖动排序（其他设备 200 ms 平滑让位，顺序保存），每台设备可设置背景图，部件状态居中显示在最上层。点击设备进入部件图，点击部件进入部件履历，每一层左上角都有返回按钮。New: the equipment overview has one page per workshop; administrators long-press (0.5 s) and drag to reorder (others make way in 200 ms, order is saved) and can set a background picture per machine, component statuses sit centred on top; machine → component map → component history, each level with a back button at the top left.
- 调整：数据源表单各输入栏左对齐，备注默认隐藏，鼠标停在输入栏 1 秒后显示。Changed: data source form inputs are aligned and the notes show only after hovering an input for 1 s.
- 新增：运行模式。管理员在“数据源”页切换“仿真演示 / 正式运行”。正式运行下设备、部件图、告警、信号配置、数据源列表和定时采集都不出现、不读取仿真内容；仿真演示下不读取涛思库并显示横幅。已登记涛思数据源的安装升级后自动为正式运行。New: run mode (simulation demo / production), switched by administrators; the two worlds are kept apart in every list and in the scheduled pipeline. An installation that already has a production source starts in production.
- 调整：“数据源”和“部件配置”（原配置工作台）放入“数据配置”，与“信号配置”同级；信号的单位、采样间隔、有效范围和数据预览只在“信号配置”维护，部件配置里只绑定数据源/设备并链接过去。Moved: 数据源 and 部件配置 sit in 数据配置 beside 信号配置; signal parameters and the preview are edited only on 信号配置.
- 新增：“从数据源生成”可指定开始/结束时间（一次最多约 92 天）。New: the generate button takes a start and end time.
- 修复：设备总览、部件图、部件履历在删除/取消后仍显示旧数据（前端缓存）。Fix: deleted or cancelled machines no longer stay on the overview, plant map or history.
- 修复：读取涛思数据按时间拆成小查询（1 秒采样的信号超过 20 万行不再失败）；读取失败时按钮旁显示原因；工况目录缓存，不再每 15 分钟重读 4 天数据。Fix: bounded, split TDengine reads (1 s sampling above 200k rows); the failure reason is shown beside the button; the regime catalog is cached.
- 调整：“检查生效情况”说明只做配置检查，并列出运行条件（RT_*）；决策树/XGBoost/LSTM/D-RCNN 目前不参与融合，会提示。Changed: "check what takes effect" is a configuration check only and lists run conditions; supervised models are flagged as not consumed.

升级步骤同 0.1.4 / Same steps as 0.1.4. 未在真实 Windows 或真实涛思服务器上运行过 / Not run on real Windows or against a real TDengine server.

## 0.1.4（2026-10-15）

升级包（只含程序代码，不含 Python/PostgreSQL，不改数据库内容与 .env）/ Upgrade package (code only; database contents and `.env` are not touched):
- 修复：数据源——主机可填 `10.26.30.97`、`host:6041` 或完整 URL，端口 6060（涛思 Explorer 网页）会被识别并提示改用 6041；测试连接逐项说明（设备标签列、信号列、取值列、时间列）；可浏览表结构；窄表（keyname + value_*）支持通配符、大小写不敏感，并可套用推荐。Fix: data sources accept host, host:port or a URL, port 6060 is recognised as taosExplorer, per-check connection diagnosis, schema browser, narrow-table layout (`value_*`, case-insensitive) with a recommendation.
- 新增：“数据源”管理页（管理员），配置工作台只选择数据源。New: administrator "Data sources" page; the workbench only picks a source.
- 修复：安装不足 4 天的新部件也能完成预测前提检查（临时特征目录，满 4 天后重建）；验证页逐项显示数据、编译、历史回放、仿真四项结果；参数优化页说明触发条件。Fix: components younger than 4 days can pass readiness (provisional regime catalog); validation lists all four checks; the tuning page explains when it can run.
- 修复：“读取该设备信号”在真实库上列出该设备的全部信号键。Fix: reading a device's signals on a real database lists its own keys.
- 修复：删除部件——有安装记录的部件现在可删除，删除前列出将一并删除的数据（安装记录、特征窗口、告警、基线、配置版本）；已有维护记录的部件仍禁止删除。提示条固定在页面顶部。Fix: components with installation records can be deleted after a confirmation that lists what goes with them; maintenance records still block.
- 新增：“算法模型”页（管理员，只读）：算法库、使用情况、LSTM / D-RCNN 适配器状态、插件。New: read-only Algorithm models page.
- 修复：配置工作台步骤顺序为 1、2、…、7；步骤 3–7 需要先建草稿，页面会提示。Fix: workbench steps run 1 to 7 in order.
- 修复：重新运行 `install.cmd` 不再丢掉 `.env` 里已有的设置（涛思账号 PDM_SECRET_*、自定义项）。Fix: re-running `install.cmd` keeps existing `.env` settings such as data source accounts.

升级：解压到任意位置（例如桌面），双击 `upgrade.cmd`。它自动找到已安装目录，备份旧程序（和数据库，若找到 pg_dump）到 `C:\ProgramData\PDM\backup\`，只替换程序文件，迁移到最新结构并重启服务。不要解压到安装目录里。
Upgrade: unzip anywhere (for example the desktop) and double-click `upgrade.cmd`. It finds the installation, backs up the old program (and the database when pg_dump is found), replaces program files only, migrates to head and restarts the service. Do not unzip into the install folder.
未在真实 Windows 上运行过。Not yet run on real Windows.

## 0.1.3（2026-10-14）

配置工作台与决策引擎重做 / Configuration workbench and decision engine redesign (D-043..D-048):
- 新增：“配置工作台”单页：车间→工序→设备→部件树，每个节点可在侧边抽屉中新增/编辑/删除；部件节点内完成数据源选择、信号映射/解除、单位/采样/有效范围、最近一小时数据预览、安装日期、特征生成、健康参考、预测配置（推荐/复制草稿→关系→算法链→判据→展示→校验→发布→启用）。
  New: single-page Configuration workbench with the plant tree (add/edit/delete in drawers) and the full per-component prediction workflow.
- 新增：管理员在工作台管理涛思数据源（新增、测试、删除；账号只写入 backend\.env）。New: administrators manage TDengine sources in the workbench (never tested against a real TDengine).
- 新增：三态安全判定；扭矩限值因数据质量无法评估时显示“安全监测降级”并给出 WATCH 告警；统一证据对象。New: three-state safety verdicts; a torque limit that cannot be evaluated shows "safety monitoring degraded" with a WATCH alert.
- 新增：Hotelling T²、关系类型驱动的共因提示、算法推荐；LSTM / D-RCNN 的可训练接口（未内置深度学习框架，占位后端报告“未注册”）。New: Hotelling T², relation-driven common-cause hints, algorithm recommendation; LSTM / D-RCNN adapter interface (no deep-learning framework bundled).
- 删除：旧的“算法配置”页（由工作台取代；查询模板 SQL 编辑、模式检查、质量报告步骤未迁移）。Removed: the old Algorithm configuration page.
- 新增：`verify.cmd` 一键测试（仿真数据，10 步流程检查后保持演示服务）。尚未在真实 Windows 上运行过。New: `verify.cmd` one-click test on SIMULATED data; not yet run on real Windows.

升级：解压覆盖原安装目录后再次双击 `install.cmd`（自动迁移数据库到 0015）。
Upgrade: unzip over the install folder and run `install.cmd` again (migrates the database to 0015).

## 0.1.2（2026-10-11）

算法修复（依据算法评审，D-040..D-042）/ Algorithm fixes from the algorithm review:
- 修复：正常老化分级不再压低 CRITICAL（只对 WARNING 生效）。Fix: aging grading no longer lowers CRITICAL.
- 修复：扭矩安全规则此前从未运行。现在可在“设备结构”为部件填写扭矩限值（与扭矩信号同单位）后生效。Fix: the torque safety rule never ran; set a torque limit per component on the plant screen to enable it.
- 新增：“基线对比”页可确认健康参考，并提示参考期内是否已有漂移或窗口太少。New: verify a healthy reference on the Baselines screen, with notes on drift inside the period or too few windows.
- 新增：在线特征流水线。服务每 15 分钟（PDM_PIPELINE_INTERVAL_MIN，0 关闭）为已映射信号的设备学习工况、提取特征并同步告警；也可 POST /api/pipeline/run。New: online feature pipeline for machines with mapped signals (every 15 min; PDM_PIPELINE_INTERVAL_MIN, 0 = off).

升级：解压覆盖原安装目录后再次双击 `install.cmd`（自动迁移数据库到 0013）。
Upgrade: unzip over the install folder and run `install.cmd` again (migrates the database to 0013).

## 0.1.1（2026-10-10）

部署后修复与新功能 / Post-deployment fixes and features:
- 修复：全新安装后数据源工作室第 4 步“查询模板”为空。服务启动时自动登记内置只读模板（D-032）。
  Fix: the Studio's query-template step was empty on a fresh install; built-in read-only templates are now registered at service start (D-032).
- 修复：“信号配置”界面仍显示占位文字；现已交付（映射、定义修改、数据预览、版本历史，D-034）。
  Fix: the Signal setup screen still showed a placeholder; it is now delivered (mapping, definition edits, data preview, version history; D-034).
- 新增：管理员“用户与权限”界面：注册、删除、改名、重置密码、停用、变更角色，以及各角色可见模块配置，服务器同步拦截（D-033）。
  New: administrator "Users and roles" screen: register, delete, rename, reset password, deactivate, change role, and per-role visible screens enforced by the server (D-033).
- 新增：所有页面固定底部栏“© 2026 MYS-TC-VSE. All rights reserved”。
  New: fixed footer "© 2026 MYS-TC-VSE. All rights reserved" on every page.
- 包含 Windows PowerShell 5.1 安装脚本修复与 httpx 依赖。Includes the PowerShell 5.1 installer fix and the httpx dependency.

升级：解压到原安装目录覆盖后，再次双击 `install.cmd`（保留数据库、密码和账号，自动迁移数据库结构）。
Upgrade: unzip over the existing install folder and double-click `install.cmd` again (keeps the database, secrets and accounts; migrates the schema).

## 0.1.0

工业预测性维护平台 V5.2 首个发布版本（T001–T028，G4 已批准）。
First release of the Industrial Predictive Maintenance Platform V5.2 (T001–T028, G4 approved).

**下载 / Downloads**
- `pdm-0.1.0-offline-win64.zip`：Windows 离线一键安装包，内置 Python 3.12.10 及全部依赖，使用服务器上已安装的 PostgreSQL 17。解压后双击 `install.cmd`。
  Offline one-click Windows installer with bundled Python 3.12.10 and all dependencies; uses the server's existing PostgreSQL 17. Unzip and double-click `install.cmd`.
- `DEPLOY_GUIDE.md`：部署说明（中英文）。Deployment guide (zh/en).

首次安装后请回传 `C:\ProgramData\PDM\install.log`。
After the first install, please send back `C:\ProgramData\PDM\install.log`.

尚未验证 / Not yet verified: installation on a real Windows host; a live Ollama model.
