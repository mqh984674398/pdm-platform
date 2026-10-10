# 模型评估（模拟数据）/ Model evaluation (SIMULATED PERFORMANCE)

以下数字全部来自模拟场景，标签取自模拟器的真值，不代表真实设备上的准确率。
All numbers come from simulated scenarios with labels from the simulator's ground truth. They are not evidence of accuracy on real equipment.

Seed 7. Lifecycle-grouped 5-fold CV (no installation in both sets); time split: train < 360 h, test ≥ 384 h. Both splits pass `assert_no_leakage`. Threshold 0.5 on uncalibrated scores. Grouped CV is the primary measure: the time split keeps the same installations on both sides, so it is optimistic.

| Type | Model | Windows (degraded) | CV precision | CV recall | CV F1 | CV ROC AUC | Time-split F1 | Time-split ROC AUC |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BALL_SCREW | dt-ball-screw@1.0.0 | 910 (315) | 0.747 | 0.889 | 0.812 | 0.873 | 0.862 | 0.909 |
| BALL_SCREW | xgb-ball-screw@1.0.0 | 910 (315) | 0.869 | 0.883 | 0.876 | 0.966 | 0.948 | 0.992 |
| LINEAR_MOTOR | — | skipped: fewer than 2 degraded installations | | | | | | |
| PNEUMATIC_CYLINDER | dt-pneumatic-cylinder@1.0.0 | 698 (203) | 0.894 | 0.207 | 0.336 | 0.599 | 0.977 | 0.980 |
| PNEUMATIC_CYLINDER | xgb-pneumatic-cylinder@1.0.0 | 698 (203) | 0.888 | 0.389 | 0.541 | 0.759 | 0.981 | 0.980 |
| VACUUM_CUP | — | skipped: fewer than 2 degraded installations | | | | | | |

Labels / 标签: SIMULATED truth: max(friction_factor) >= 1.15 in the window -> degraded; SIMULATED truth: max(extend_factor, retract_factor) >= 1.15 in the window -> degraded
