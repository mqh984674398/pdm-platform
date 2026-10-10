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
