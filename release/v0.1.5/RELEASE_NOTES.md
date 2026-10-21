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

