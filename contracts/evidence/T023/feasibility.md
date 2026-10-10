# T023 CNN/LSTM 可行性评估 / CNN/LSTM feasibility (L5-04, STK-03)

日期 Date: 2026-10-09 · 结论 Conclusion: **不引入 / not justified** (D-025). 不添加 PyTorch 依赖 / no PyTorch dependency is added.

全部数据为模拟数据。下列数字由 `sampling_stats.py` 和 T022 的 `evaluation.json` 计算得出。
All data is simulated. The numbers below come from `sampling_stats.py` (output in `sampling_stats.txt`) and T022's `evaluation.json`.

## 1. 采样质量与分辨率 / Sampling quality and resolution

- 遥测是按工序的短时突发采样：中位间隔 2–6 s，每信号每天约 77–249 个样本（20 个场景合计 216 810 个样本）。The telemetry is short per-operation bursts: median interval 2–6 s, about 77–249 samples per signal per day (216 810 samples over all 20 scenarios).
- 没有振动、声学或高频电流波形。CNN/LSTM 的典型优势（从原始高频波形中学习形状特征）在这里没有可用的输入。There is no vibration, acoustic or high-rate current waveform. The usual advantage of a CNN/LSTM, learning shape features from raw high-rate signals, has no input to work on here.
- 采样不规则（S13 缺失/重复、S14 抖动/乱序、S20 中断），序列模型需要重采样或插值，会引入人为数据。 Sampling is irregular (S13 missing/duplicates, S14 jitter/out-of-order, S20 interruptions); a sequence model would need resampling or imputation, which manufactures data.
- 真实 IoT 库的采样率尚未核实（G2 A1–A3）。The real IoT database's sampling has not been verified (G2 A1–A3).

## 2. 数据量 / Data volume

| 类型 Type | 特征窗口 Windows | 劣化窗口 Degraded | 安装次数 Installations | 劣化安装 Degraded installations |
| --- | --- | --- | --- | --- |
| 滚珠丝杠 Ball screw | 910 | 315 | 17 | ≥2 |
| 气缸 Pneumatic cylinder | 698 | 203 | 11 | ≥2 |
| 直线电机 Linear motor | — | — | — | <2 |
| 真空吸盘 Vacuum cup | — | — | — | <2 |

独立的样本单位是安装（生命周期），不是窗口。每类只有十几个安装、几个劣化安装，远不足以训练和验证深度模型；T022 的树模型在气缸上已经因为劣化安装太少而召回偏低。
The independent unit is the installation (lifecycle), not the window. Each type has about a dozen installations and only a few degraded ones, far too few to train and validate a deep model; T022's tree models already show low cylinder recall because degraded installations are scarce.

## 3. 与 T022 对比 / Comparison with T022

| 类型 Type | 模型 Model | 分组 CV F1 | 分组 CV ROC AUC |
| --- | --- | --- | --- |
| 滚珠丝杠 Ball screw | 决策树 Decision tree | 0.812 | 0.873 |
| 滚珠丝杠 Ball screw | XGBoost | 0.876 | 0.966 |
| 气缸 Pneumatic cylinder | 决策树 Decision tree | 0.336 | 0.599 |
| 气缸 Pneumatic cylinder | XGBoost | 0.541 | 0.759 |

滚珠丝杠上，可解释的特征 + XGBoost 已经在模拟数据上达到 AUC 0.97，深度模型几乎没有提升空间。气缸的瓶颈是劣化安装的数量，不是模型容量，换成 CNN/LSTM 不会解决。
On the ball screw, interpretable features with XGBoost already reach AUC 0.97 on simulated data, leaving little room for a deep model. The cylinder bottleneck is the number of degraded installations, not model capacity; a CNN/LSTM does not fix that.

未训练 CNN/LSTM 做实测对比：在上述数据量下，任何分组 CV 结果都无法与噪声区分，而添加 PyTorch 本身需要依据（STK-03）。 No CNN/LSTM was trained for a head-to-head run: at this volume a grouped-CV result could not be told apart from noise, and adding PyTorch itself needs a justification (STK-03).

## 4. 其他考虑 / Other considerations

- 部署：Windows 局域网服务器，CPU 推理；PyTorch 约增加 1–2 GB 安装体积。Deployment: Windows LAN server with CPU inference; PyTorch adds roughly 1–2 GB to the install.
- 可解释性：证据链要求每个结论可追溯到特征和规则（G3 已批准），深度模型的输出更难解释。Explainability: the evidence trail must trace each conclusion to features and rules (approved at G3); deep-model outputs are harder to explain.

## 5. 重新评估条件 / When to revisit

若真实数据满足以下条件，再重新评估：高频波形（≥1 kHz 振动或电流）可用；每类至少几十个有记录的劣化或失效安装；采样经 G2 A1–A3 核实。届时作为新的操作符接入 T021 路由（`backend/app/prediction/dl`），并按 T022 的分组验证对比。
Revisit if real data provides: high-rate waveforms (vibration or current at ≥1 kHz); at least several dozen documented degraded or failed installations per type; sampling verified per G2 A1–A3. It would then plug into T021 routing as a new operator (`backend/app/prediction/dl`) and be compared with T022 under the same grouped validation.
