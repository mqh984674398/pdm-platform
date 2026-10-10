# G4 生产发布验收 · Production release acceptance

日期 Date: 2026-10-10 · 版本 Version: 0.1.0 · 任务 Tasks: T001–T028 全部完成 / all DONE

**请决定 · Decision needed**：是否批准 G4 发布（在局域网 Windows 服务器上以模拟数据和本地账号运行）。
批准 G4 **不会**开启生产数据连接或正式维护告警；这两项需要您另外明确批准。
Approve the G4 release (LAN Windows server, local accounts, simulated data). Approving G4 does **not**
enable a production data connection or official maintenance alerting; each needs your separate explicit approval.

> 所有结果均基于**模拟数据**。All results come from **SIMULATED** data. No real plant data was used.

## 验收清单 · Checklist (ACCEPTANCE.md §G4)

| # | 项目 Item | 结果 Result | 证据 Evidence |
|---|---|---|---|
| 1 | 历史回放 Historical replay | 20 个 Golden Case 共 1310 个窗口：当前配置 1199 个在预期范围内 (91.5%)。推荐的候选 A05 为 1205，未应用。<br>Champion 1199/1310 windows within expectations; recommended challenger A05 reaches 1205/1310 and was not applied. | `contracts/evidence/T025/`, `T024/golden_fused.json`, screenshot `03_optimization.png` |
| 2 | 机器学习评估 ML evaluation (simulated labels) | 滚珠丝杠 XGBoost 分组交叉验证 F1 0.876 / AUC 0.966；气缸召回率仅 0.389（弱，未接入健康判定）。不集成 CNN/LSTM。<br>Ball screw XGBoost grouped-CV F1 0.876 / AUC 0.966; cylinder recall only 0.389 (weak; not wired into health decisions). No CNN/LSTM (D-025). | `contracts/evidence/T022/evaluation.md`, `T023/feasibility.md` |
| 3 | 受控优化 Champion–challenger and rollback | 工程师提议、管理员带意见和通过的门槛才能上线、工程师一步回滚，安全规则不可改。E2E 已验证上线和回滚。<br>Engineer proposes; admin promotes only with a comment and a passed gate; engineer rolls back one step; safety rules are invariant. Promote and rollback verified end to end. | `tests/registry` (10), E2E `models.spec.ts`, screenshot `04_models.png` |
| 4 | Ollama 本地运行与 RAG 引用 Local Ollama and RAG with citations | 仅接受本机/局域网地址，拒绝云端模型；文档需管理员批准并按角色过滤；回答带引用并经过校验。**使用模拟 Ollama 测试；未连接真实 Ollama。**<br>LAN-only endpoints, cloud tags refused, admin-approved role-filtered documents, cited and validated answers. **Tested against a fake Ollama; no live Ollama was run.** | `tests/llm` (35 passed, 1 live test skipped), `contracts/evidence/T027/` |
| 5 | LLM 故障降级 Fallback without Ollama | Ollama 不可用时监控、健康判定、报警全部正常；助手返回“不可用”。<br>Monitoring, health and alarms work with Ollama down; the assistant reports it is unavailable. | `test_platform_works_with_ollama_down`; deployment log; screenshot `05_assistant_no_ollama.png` |
| 6 | 安全检查 Security checks | 15 项发现：11 项已解决，4 项为需您接受的残余风险（见下），0 项未处理。<br>15 findings: 11 resolved, 4 accepted residual risks (below), none open. | `contracts/evidence/T028/security_review.md` |
| 7 | Windows/局域网部署 Windows/LAN deployment | 部署包已生成；在 Linux 上以生产模式（本地账号、PostgreSQL、单端口前端）运行 26 项检查全部通过；所有依赖都有 Windows 安装包。**install.ps1 尚未在 Windows 上实际运行。**<br>Package built; production-mode run on Linux passed 26/26 checks; every dependency has a Windows wheel. **install.ps1 has not been run on Windows yet.** | `dist/pdm-0.1.0-windows.zip`, `deploy/README.md`, `T028/deployment_log.txt`, `T028/windows_wheels_cp312.txt` |
| 8 | 端到端验收 End-to-end evidence | 完整 CI：后端 532 通过 / 1 跳过（需真实 Ollama），前端单元 44，E2E 15，全部通过。<br>Full CI: backend 532 passed / 1 skipped (live Ollama), frontend unit 44, E2E 15, all green. | `contracts/evidence/T028/ci_local.log`, screenshots `01`–`05` |
| 9 | 生产数据与正式告警需明确批准 Explicit approval for production data and alerting | 保持关闭：`PDM_PRODUCTION_DATA_APPROVED=false`（安装程序不会修改），配置中的生产数据源被跳过；代码中没有任何通知渠道。<br>Kept off: production sources are skipped while `PDM_PRODUCTION_DATA_APPROVED=false` (never set by the installer); no notification channel exists. | `test_production_sources_stay_off_until_approved`; deployment log |

## 需要您接受的残余风险 · Residual risks to accept

1. **HTTP 明文传输** Plain HTTP on the LAN until plant IT provides a certificate (SR-10).
2. **未做依赖漏洞扫描** No dependency vulnerability scan was run offline; run `pip-audit` before each release (SR-14).
3. **会话令牌在 12 小时内有效** A copied session token stays valid until it expires (12 h); deactivating the account revokes it at once (SR-15).
4. **Ollama 主机防火墙** The Ollama host must be bound to localhost or firewalled by the operator (SR-07).

## 尚未验证 · Not yet verified (honest gaps)

- Windows 实机安装（install.ps1、计划任务、防火墙规则）。The first install on a real Windows server.
- 真实 Ollama 服务。A live Ollama server.
- 真实 IoT 数据库结构（G2 假设 A1–A3）。The real IoT database schema (G2 assumptions A1–A3) needs read-only access or a sample export.
- GitHub 尚未连接，代码在本地仓库和项目文件中（`repo/`, `repo-bundle/pdm.bundle`）。GitHub is not connected; the code is in the local repository and the project files.

## 截图 · Screenshots (production-mode package, simulated data)

`01_sign_in.png` 登录 Sign-in · `02_overview_signed_in.png` 车队总览 Fleet overview · `03_optimization.png` 参数优化 Parameter tuning · `04_models.png` 模型版本 Model versions · `05_assistant_no_ollama.png` 无 Ollama 时的助手 Assistant without Ollama
