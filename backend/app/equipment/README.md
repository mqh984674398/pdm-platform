# Equipment (L3)

Operating state, operating regimes, and movement cycles of a machine over a period (T013). Everything
is derived from full-resolution signals read through the read-only adapters (`state.load_series`).
`operations.analyze_machine` runs all three and returns a `MachineOperations` contract.

## Operating state (`state.py`)

Rows come in observation windows separated by pauses (max(60 s, 30 sample intervals)). Each window
gets one state from its own evidence; time between windows has none.

| State | Evidence |
| --- | --- |
| RUNNING | A speed signal shows real motion (95th percentile above 20 noise levels), or an actuator reported operations. |
| IDLE | Speed signals report but stay within their noise, and no actuator operated. |
| MAINTENANCE | A maintenance record covers the time. Records win over telemetry. |
| UNKNOWN | No data, only missing values, or no speed signal and no operations. |
| STOPPED, FAULT | Never derived: they need a machine status or alarm signal that the sources do not have. A stopped machine that sends nothing reads as UNKNOWN. |

## Operating regimes (`regimes.py`)

Per running window: cruise speed of each speed signal, torque at cruise of each torque signal, the
interval between actuator operations (it follows the machine cycle), and the median completed
duration of each actuator signal.

A catalog is learned from a reference period the user confirms as known operation. Windows are
grouped by speed and interval; groups seen at least 3 times become known regimes. Speeds are sampled
at fixed intervals, so a window can miss the cruise phase and see a lower peak (up to about 30 %
lower); such windows join the regime above them, and torque from them is not used because it
includes acceleration torque.

Only speed and interval decide the regime. Torque and durations also change when a component
degrades; if they defined regimes, degradation would be hidden as a "new regime" (checked on S04).
They are normalized against the matched regime's reference level instead (`normalized` on each
feature, L4-03), which keeps a recipe change from looking like degradation (S02).

| Status | Meaning |
| --- | --- |
| KNOWN | Speeds and intervals fit a known regime. |
| UNSUPPORTED | Running, but no known regime fits (S17). Health and predictions must abstain (`UNSUPPORTED_REGIME`). |
| NOT_EVALUATED | Not running, no speed signal (actuator-only machines), or no catalog. |

## Movement cycles (`cycles.py`)

Each value of an actuator duration signal is one operation: EXTEND, RETRACT or VACUUM_RELEASE (kind
from the signal id or name, or configured with `CycleSignal`). An operation that did not finish is
reported with the controller's timeout. With a configured `timeout_s` those values are incomplete;
without one, the value repeated among durations at least 3× the period median is taken as the
timeout. Incomplete operations get no duration and never enter duration statistics (S18). Other
far-off values (for example a unit error, S16) are marked implausible and also kept out of
statistics. A summary is `sufficient` with at least 10 usable operations.

Motion segments are runs of samples in one direction on a speed signal; a run touching the window
edge is incomplete because its start or end was not observed.

Verification: `pytest tests/equipment`; `python scripts/operations_sweep.py` lists states, regimes
and cycles for every simulated scenario.
