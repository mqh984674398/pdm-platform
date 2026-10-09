# Monitoring (L4)

## Data quality (`quality/`, T012)

`POST /api/quality/report` checks saved or draft signals over a window (at most 168 h). Rows are read
at full resolution through the read-only adapters; the period before the window (`lookback_hours`,
default 168) is read only as a reference. Findings are reported and never corrected.

| Flag | How it is decided |
| --- | --- |
| MISSING | Inside each observation window, fewer rows than the expected interval implies (more than 2 % absent), or null values. Not evaluated for event-based signals. |
| DUPLICATE | Rows with the same timestamp. |
| OUT_OF_ORDER | A row stored after a row with a later timestamp. Needs storage order: the simulator's file order, or `arrival_column` in a SQL layout; otherwise listed in `not_evaluated`. |
| JITTER | Robust spread (MAD) of intervals inside observation windows above 5 % of the expected interval. Not evaluated for event-based signals. |
| GAP | A pause longer than 4× the usual pause between observation windows (6× for event-based signals, which are silent while the machine idles), at least 1 h; 24 h when the usual pause is unknown. A pause running into the window is measured from the last row before it. |
| OUT_OF_RANGE | Outside the signal's `valid_min`/`valid_max`, else a unit default (`s` 0–60, `ms` 0–60000, `rpm` ±20000, `mm/s` ±10000). |
| UNIT_SUSPECT | Level of a strictly positive quantity (duration, pressure) changing 20× between observation windows or against the reference period. Speed and torque legitimately drop to zero, so this check is not applied to them. |

Observation windows are runs of rows separated by pauses longer than max(60 s, 30 sample intervals).

## Alignment (`alignment/`, T012)

Speed/torque pairs (same component, or given explicitly) are paired by nearest timestamp within a
tolerance (half the expected interval, default 1 s). In each observation window with real motion,
a clearly moving axis must show torque away from its standstill level and an axis at rest (speed
within its noise) must not show motion torque. A window where fewer than 80 % of pairs agree is
MISALIGNED. The standstill torque is compared with the reference period: a shift larger than
3× its spread (and 5 % of the motion torque) is BIAS_SUSPECT.

Thresholds were set on the simulated scenarios: every Golden Case of S13–S16 and S20 is met and the
15 scenarios without data faults raise no flags (`backend/scripts/quality_sweep.py`). They are not
validated on real equipment.
