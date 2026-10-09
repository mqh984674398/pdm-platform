# Data/ — Simulation Workspace · 模拟数据工作区

> **SIMULATED DATA ONLY.** Everything in this directory is produced by a deterministic generator for development, tests, and demonstrations. It is not real industrial data and must never be presented as real equipment behavior, predictive accuracy, or maintenance performance (GEN-03).
>
> **仅限模拟数据。** 本目录中的所有数据均由确定性生成器产生，仅用于开发、测试和演示，不是真实工业数据，不得作为真实设备行为、预测准确率或维护效果展示。

| Path | Content |
|---|---|
| `manifest.json` | Registry of generated datasets with seeds, config hashes, file checksums |
| `config/` | Simulation configs (JSON, schema `backend/app/simulation/config.py`) |
| `simulated/<dataset_id>/` | Generated datasets |
| `scenarios/` | The 20 required scenarios (T005) |
| `fixtures/` | Small test fixtures (T005) |
| `golden_cases/` | Golden Cases with expected responses (T005) |

## Generate

```bash
cd backend
python -m app.simulation ../Data/config/demo_small.json   # writes Data/simulated/demo_small + manifest
```

Same config and seed produce byte-identical files (tested in `backend/tests/test_simulator.py`).

## Dataset files

| File | Representation |
|---|---|
| `raw_telemetry.csv` | Raw IoT-style rows `deviceid,keyname,ts,datatype,value_double` in arrival order (fault injection can make rows out of order or duplicated). Raw units: speed rpm, torque % of rated, linear speed mm/s, durations ms. |
| `normalized.csv` | Same rows mapped to logical signals with unit conversion applied (`signal_id,ts,value,unit,...`). No cleaning: quality problems remain for L4 to detect. |
| `topology.json` | Machines, components, lifecycles, signal definitions, signal mappings (T003 contract schemas) |
| `maintenance_events.json` | Maintenance events (T003 `MaintenanceEvent`) |
| `truth_windows.csv` | Ground truth per observation window: operating state and recipe |
| `truth_components.csv` | Ground truth per window and component: lifecycle, wear, degradation factors |
| `faults.json` | Injected data faults and incomplete operations |
| `config.json`, `dataset.json` | Exact config and dataset metadata (seed, generator version, checksums) |

Timestamps are UTC with millisecond precision. Device ids always start with `SIM-`.

## Model summary (not calibrated to any real machine)

- **Ball screw:** trapezoidal moves alternating direction; torque = friction factor × (Coulomb + viscous) + inertia + load. Friction factor = 1 + wear + friction + lubrication + part spread.
- **Linear motor:** trapezoidal speed profile with speed ripple while cruising; ripple grows with wear and the `ripple` parameter.
- **Vacuum cup:** one release duration per cycle, scaled by release factor and workpiece factor.
- **Pneumatic cylinder:** separate extension and retraction durations per cycle with direction-specific factors and supply-pressure factor.
- **Cam / gear:** topology templates only, no telemetry (REQUIREMENTS §14).
- **Aging** accumulates wear for the installed part; **lubrication** changes reversible parameters but never wear (L3-08); **replacement** starts a new lifecycle with fresh wear and cancels earlier faults; **partial repair** may reduce wear.
- **Incomplete operations** are reported with the controller timeout value. This representation is an assumption until the real controller behavior is known.
- **Data faults:** missing, duplicate, jitter, out-of-order, speed/torque sync offset, bias, unit scale, interruption.
