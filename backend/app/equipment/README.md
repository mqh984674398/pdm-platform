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

## Topology and lifecycles (`lifecycle.py`, T014)

Machines, components, lifecycles, maintenance events and workflows are stored in the application
database (migration `0003`); every change writes an audit row in the same transaction.

- A component gets its first lifecycle with `POST /api/components/{id}/lifecycles`. Every later
  installation comes from a REPLACEMENT event: the installed lifecycle is retired at the event time and
  `<component>-LC<n+1>` starts with `predecessor_lifecycle_id` pointing back. Retired lifecycles, their
  events and their accumulated operation stay readable.
- Accumulated operation is added with `POST /api/lifecycles/{id}/usage` for the period since
  `usage_counted_until`, so each period is counted once. `running_hours()` gives the derived RUNNING
  time from T013 states; on S12 it is within 5 % of the simulator's count per lifecycle.
- `GET /api/components/{id}/aging?at=` reports calendar and operating age of the lifecycle installed
  at that time. Lubrication, adjustment, partial repair and inspection never reset it (L3-08).

## Maintenance events and workflow (`maintenance.py`, T014)

`POST /api/maintenance-events` (maintenance role) records an event in time order, never in the future
or before the current installation. Every event except INSPECTION starts a workflow:

```
MAINTENANCE_EVENT → STABILIZATION → POST_MAINTENANCE_VALIDATION → NORMAL_MONITORING
                                                               ↘ REVIEW_REQUIRED → NORMAL_MONITORING
```

`POST /api/maintenance-workflows/{id}/transitions` moves one step; any other move is refused (409) and
nothing is recorded. Closing REVIEW_REQUIRED is a human review: engineer role and a comment. A new event
supersedes the component's open workflow. Stabilization and validation are moved by people until T018
automates the checks. The workflow only tracks state; it sends no alerts.

## Maintenance impact (`maintenance_impact/`, T018)

`analyze_impact` compares condition-normalized residuals (cruise torque, actuator duration medians)
in the 72 h before an event with the period after stabilization, only within regimes seen on both
sides (at least 3 windows before). Outcomes: IMPROVED, PARTIAL (improved but still at least 3 robust
units above the reference), NO_CHANGE, DETERIORATED (change at least +2), UNKNOWN (fewer than 3
comparable windows after). `ImpactService.advance` drives the workflow: stabilization, then validation, then
NORMAL_MONITORING (IMPROVED or NO_CHANGE) or REVIEW_REQUIRED (PARTIAL, DETERIORATED, or still UNKNOWN
after 120 h). Settings are in `ImpactConfig`.

