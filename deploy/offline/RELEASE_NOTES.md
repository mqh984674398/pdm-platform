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
