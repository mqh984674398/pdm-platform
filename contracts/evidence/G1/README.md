# G1 前端演示 / Frontend demonstration

日期 Date: 2026-10-09 · 任务 Tasks: T001–T008 · 状态 Status: 等待用户决定 / awaiting user decision

在线演示 Live demo (private, simulated data): https://claude.ai/artifact/HWKJ5WfC7WioDW5xwVrZN5
本地运行 Run locally: `cd frontend && npm ci && npm run dev`, then open http://localhost:5173

所有数据均为模拟数据，界面上有“模拟数据”标识。设备健康状态取自各模拟场景的预期结果（Golden Case），不是监测引擎的计算结果；监测引擎在 T017–T024 交付。

All data is simulated and labeled in the UI. Machine health is each simulated scenario's expected result (Golden Case), not computed by a monitoring engine; the engine arrives in T017–T024.

## 1. 检查清单 / Checklist (ACCEPTANCE.md §G1)

| 项目 Item | 证据 Evidence | 结果 Result |
| --- | --- | --- |
| 多设备总览 Multi-machine overview | `overview-zh.png`, `overview-en-dark.png`; E2E `fleet.spec.ts` | 8 台模拟设备、按最差状态汇总 / 8 simulated machines, worst-state summary |
| 交互式 SVG 部件健康图（覆盖全部状态）Interactive SVG component map, all states | `machine-A06-zh.png`, `machine-A02-en-dark.png`, `component-A05-zh.png`; backend `test_every_health_state_is_demonstrated` | 正常/关注/警告/严重/未知 全部出现 / NORMAL, WATCH, WARNING, CRITICAL, UNKNOWN all shown |
| SQL 数据源工作室引导流程（普通用户无需 SQL）Data Source Studio, no SQL for ordinary users | `studio-*.png`; E2E `studio.spec.ts` (12 steps as operator; SQL only for administrator) | 12 步全部可走通 / all 12 steps complete |
| 来自 Data/ 场景的有意义模拟数据并清晰标注 Meaningful, labeled simulated data | `Data/fixtures/demo_fleet.json`, `studio_demo.json`; quality step finds the faults built into S13, S14, S16 | 通过 / pass |
| 中英文切换无需刷新 zh/en switch without reload | E2E `shell.spec.ts` (window marker survives switch) | 通过 / pass |
| 重大界面与流程决策 Major UX and workflow decisions | §2 below | **等待用户 / awaiting user** |

本地 CI（`tools/ci_local.sh`，D-007）最近一次：后端 71 项通过（Python 3.11 与 3.12），前端单元测试 29 项、端到端 5 项通过，类型检查、lint、构建通过。日志 `contracts/evidence/T008/ci_local.log`。

Latest local CI (`tools/ci_local.sh`, D-007): backend 71 passed on Python 3.11 and 3.12; frontend 29 unit and 5 end-to-end tests passed; typecheck, lint, and build clean. Log: `contracts/evidence/T008/ci_local.log`.

## 2. 需要您决定的界面选择 / UX choices for your decision

每项都附上推荐方案。批准 G1 即表示接受以下推荐；如需修改，请指出编号。
Each has a recommendation. Approving G1 accepts the recommendations below; to change one, name its number.

1. **视觉风格 Visual direction.** 浅色工业仪表风格为默认，提供深色模式；健康颜色遵循 ISO 3864，“未知”用斜线纹理而不是第五种颜色。
   Light industrial instrument-panel look by default, with dark mode; health colors follow ISO 3864, and UNKNOWN is a hatch pattern rather than a fifth color.
   推荐 Recommended: 保持 keep.
2. **设备部件图 Machine map.** 示意式“工位牌”：每个部件一块牌子，排在机床底座上，共享传动链用连线标出。另一种做法是按机型绘制真实外观图，但每个机型都需要单独绘图。
   Schematic station plates, one per component on a machine bed, with shared drive chains drawn as links. The alternative is a realistic drawing per machine model, which needs custom artwork for each model.
   推荐 Recommended: 示意式 schematic.
3. **数据源工作室流程 Studio workflow.** 12 步线性向导，可随时返回已完成的步骤，未完成时“下一步”不可点并提示原因。后续可为管理员增加单页高级编辑模式。
   A 12-step linear wizard with free return to completed steps; Next stays disabled with a hint until a step is complete. A one-page advanced editor for administrators can be added later.
   推荐 Recommended: 向导 wizard, 高级模式放到后续 advanced mode later.
4. **总览汇总规则 Overview summary rule.** 设备状态取已知部件中最差的状态；“未知”从不算作正常，只有全部未知时设备才显示为未知。
   Machine state is the worst known component state; UNKNOWN never counts as healthy, and a machine shows UNKNOWN only when nothing is known.
   推荐 Recommended: 保持 keep.

## 3. 已知限制 / Known limitations

- 后端尚未提供数据接口；演示使用与契约一致的模拟后端（T009–T011 替换）。The backend APIs are not built yet; the demo uses a mocked backend that follows the contracts (replaced in T009–T011).
- 演示中的质量检查是界面层的简化实现，T010 由 L2 质量服务替代。The quality summary in the demo is a simplified UI-side version; the L2 quality service replaces it in T010.
- 真实 IoT 数据库结构尚未核实；需要只读访问或样例导出，最迟在 G2 前。The real IoT database schema is unverified; read-only access or a sample export is needed before G2.
- 代码尚未推送到 GitHub：项目还没有连接仓库。完整历史保存在项目文件 `repo-bundle/pdm.bundle`。The code is not on GitHub yet because no repository is connected; full history is in the project files at `repo-bundle/pdm.bundle`.
- 版本历史中的第 1、2 版是演示用的模拟记录。Versions 1 and 2 in the studio history are simulated records for the demo.

## 4. 批准后 / After approval

按契约在 G1 停止，等待您的明确决定；沉默不视为批准。批准后从 T009（后端数据源与只读查询模板）继续，T009–T014 不依赖上述界面选择，修改意见可以并行处理。

Work stops at G1 until you decide; silence is not approval. After approval, work continues with T009 (backend data sources and read-only query templates). T009–T014 do not depend on the choices above, so any UX changes can be made alongside.

## 5. 截图 / Screenshots in this folder

`overview-zh.png`, `overview-en-dark.png`, `machine-A06-zh.png` (shared drive chain), `machine-A02-en-dark.png` (critical component detail), `component-A05-zh.png` (replacement lifecycle), `studio-01-connection-zh.png`, `studio-04-template-en-admin.png`, `studio-06-units-zh.png`, `studio-08-preview-en.png`, `studio-09-quality-zh.png`, `studio-12-version-en.png`. Full sets: `contracts/evidence/T007/`, `contracts/evidence/T008/`.
