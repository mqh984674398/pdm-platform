"""T004 simulator tests: determinism, schema conformity, labeling, effects, faults, adapter."""

import csv
import json
from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.schemas import TimeWindow
from app.datasource.adapter import TimeSeriesAdapter
from app.datasource.simulated import SimulatedAdapter
from app.equipment.schemas import ComponentLifecycle, MaintenanceEvent
from app.signals.schemas import SignalDefinition, SignalMapping
from app.simulation.config import SimulationConfig
from app.simulation.generator import generate
from app.simulation.writer import update_manifest, write_dataset

DATA = Path(__file__).resolve().parents[2] / "Data"
DEMO = json.loads((DATA / "config" / "demo_small.json").read_text(encoding="utf-8"))


def cfg(**overrides) -> SimulationConfig:
    return SimulationConfig.model_validate(DEMO | overrides)


def write(tmp_path: Path, config: SimulationConfig, name: str = "ds") -> Path:
    out = tmp_path / name
    meta = write_dataset(generate(config), out)
    update_manifest(tmp_path, meta, f"simulated/{name}")
    return out


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


@pytest.fixture(scope="module")
def demo_dir(tmp_path_factory) -> Path:
    return write(tmp_path_factory.mktemp("demo"), cfg())


def test_same_seed_is_byte_identical(tmp_path):
    a, b = write(tmp_path, cfg(), "a"), write(tmp_path, cfg(), "b")
    for f in sorted(p.name for p in a.iterdir()):
        assert (a / f).read_bytes() == (b / f).read_bytes(), f


def test_different_seed_changes_values(tmp_path):
    a, b = write(tmp_path, cfg(), "a"), write(tmp_path, cfg(seed=1), "b")
    assert (a / "raw_telemetry.csv").read_bytes() != (b / "raw_telemetry.csv").read_bytes()


def test_committed_demo_dataset_matches_generator(demo_dir):
    committed = DATA / "simulated" / "demo_small"
    for f in ["raw_telemetry.csv", "normalized.csv", "topology.json", "truth_components.csv"]:
        assert (committed / f).read_bytes() == (demo_dir / f).read_bytes(), f


def test_everything_is_labeled_simulated(demo_dir):
    meta = json.loads((demo_dir / "dataset.json").read_text(encoding="utf-8"))
    assert (
        meta["is_simulated"] is True
        and "SIMULATED" in meta["notice"]["en"]
        and "模拟" in meta["notice"]["zh"]
    )
    assert {r["is_simulated"] for r in rows(demo_dir / "normalized.csv")} == {"true"}
    assert all(r["deviceid"].startswith("SIM-") for r in rows(demo_dir / "raw_telemetry.csv"))
    for e in json.loads((demo_dir / "maintenance_events.json").read_text(encoding="utf-8")):
        assert MaintenanceEvent.model_validate(e).is_simulated
    manifest = json.loads((demo_dir.parent / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["is_simulated_workspace"] and all(d["is_simulated"] for d in manifest["datasets"])


def test_topology_conforms_to_contract_schemas(demo_dir):
    topo = json.loads((demo_dir / "topology.json").read_text(encoding="utf-8"))
    assert len(topo["machines"]) == 2
    for s in topo["signals"]:
        SignalDefinition.model_validate(s)
    for m in topo["mappings"]:
        SignalMapping.model_validate(m)
    for lc in topo["lifecycles"]:
        ComponentLifecycle.model_validate(lc)
    types = {c["type"] for c in topo["components"]}
    assert types == {"BALL_SCREW", "LINEAR_MOTOR", "VACUUM_CUP", "PNEUMATIC_CYLINDER", "CAM", "GEAR"}


def test_template_only_components_have_no_telemetry(demo_dir):
    topo = json.loads((demo_dir / "topology.json").read_text(encoding="utf-8"))
    for c in topo["components"]:
        if c["type"] in ("CAM", "GEAR"):
            assert c["signal_ids"] == []
    keys = {r["keyname"] for r in rows(demo_dir / "raw_telemetry.csv")}
    assert not any("CAM" in k or "GR1" in k for k in keys)


def test_normalized_is_raw_with_mapping_conversion(demo_dir):
    topo = json.loads((demo_dir / "topology.json").read_text(encoding="utf-8"))
    by_key = {m["key_name"]: m for m in topo["mappings"]}
    raw, norm = rows(demo_dir / "raw_telemetry.csv"), rows(demo_dir / "normalized.csv")
    assert len(raw) == len(norm)
    for r, n in zip(raw[::97], norm[::97], strict=True):
        m = by_key[r["keyname"]]
        assert n["signal_id"] == m["signal_id"] and n["ts"] == r["ts"]
        assert float(n["value"]) == pytest.approx(
            float(r["value_double"]) * m["conversion"]["scale"], rel=1e-9
        )
        assert n["unit"] == m["conversion"]["target_unit"]


def test_units_physically_plausible(demo_dir):
    norm = rows(demo_dir / "normalized.csv")
    rel = [float(r["value"]) for r in norm if r["signal_id"] == "M01-VC1.release_time"]
    ext = [float(r["value"]) for r in norm if r["signal_id"] == "M01-CY1.extend_time"]
    spd = [abs(float(r["value"])) for r in norm if r["signal_id"] == "M01-LM1.speed"]
    assert 0.05 < min(rel) and max(rel) < 0.15  # seconds
    assert 0.25 < min(ext) and max(ext) < 0.6
    assert max(spd) < 1.0  # m/s


def test_multiple_regimes_and_states_present(demo_dir):
    w = rows(demo_dir / "truth_windows.csv")
    assert {r["recipe_id"] for r in w if r["machine_id"] == "M01"} == {"R-A", "R-B"}
    assert {"RUNNING", "IDLE"} <= {r["state"] for r in w}


def test_lubrication_improves_without_resetting_wear(demo_dir):
    truth = [r for r in rows(demo_dir / "truth_components.csv") if r["component_id"] == "M01-BS1"]
    before = [r for r in truth if r["window_start"] < "2026-01-06T12:30"]
    after = [r for r in truth if r["window_start"] > "2026-01-06T13:00"]
    assert float(after[0]["friction_factor"]) < float(before[-1]["friction_factor"])
    assert float(after[0]["wear"]) > float(before[-1]["wear"])  # aging continues (L3-08)


def test_replacement_creates_new_lifecycle_and_preserves_history(demo_dir):
    topo = json.loads((demo_dir / "topology.json").read_text(encoding="utf-8"))
    lcs = [lc for lc in topo["lifecycles"] if lc["component_id"] == "M02-CY1"]
    assert [lc["status"] for lc in lcs] == ["RETIRED", "ACTIVE"]
    assert lcs[1]["predecessor_lifecycle_id"] == lcs[0]["lifecycle_id"]
    truth = [
        r["lifecycle_id"] for r in rows(demo_dir / "truth_components.csv") if r["component_id"] == "M02-CY1"
    ]
    assert truth[0] == "M02-CY1-LC1" and truth[-1] == "M02-CY1-LC2"


def test_torque_tracks_friction_drift(tmp_path):
    drift = DEMO | {
        "effects": [
            {"target": "M02-BS1", "parameter": "friction", "shape": "STEP", "start_h": 36, "magnitude": 0.8}
        ],
        "maintenance": [],
    }
    out = write(tmp_path, SimulationConfig.model_validate(drift))
    norm = rows(out / "normalized.csv")
    trq = [(r["ts"], abs(float(r["value"]))) for r in norm if r["signal_id"] == "M02-BS1.torque"]
    early = [v for t, v in trq if t < "2026-01-06T12:00" and v > 1.0]
    late = [v for t, v in trq if t > "2026-01-06T12:00" and v > 1.0]
    assert sum(late) / len(late) > sum(early) / len(early) * 1.05


def test_data_faults_are_applied_and_logged(tmp_path):
    faults = DEMO | {
        "data_faults": [
            {
                "kind": "INTERRUPTION",
                "device_id": "SIM-M01",
                "key_names": ["M01_LM1_SPD"],
                "start_h": 0,
                "end_h": 24,
            },
            {
                "kind": "DUPLICATE",
                "device_id": "SIM-M01",
                "key_names": ["M01_VC1_REL"],
                "start_h": 0,
                "end_h": 72,
                "rate": 0.2,
            },
            {
                "kind": "UNIT_SCALE",
                "device_id": "SIM-M02",
                "key_names": ["M02_BS1_TRQ"],
                "start_h": 0,
                "end_h": 72,
                "scale": 10.0,
            },
        ]
    }
    base, out = (
        write(tmp_path, cfg(), "base"),
        write(tmp_path, SimulationConfig.model_validate(faults), "faulty"),
    )

    def series(d, key):
        return [r for r in rows(d / "raw_telemetry.csv") if r["keyname"] == key]

    assert not [r for r in series(out, "M01_LM1_SPD") if r["ts"] < "2026-01-06T00:00"]
    assert len(series(out, "M01_VC1_REL")) > len(series(base, "M01_VC1_REL"))
    b, f = series(base, "M02_BS1_TRQ"), series(out, "M02_BS1_TRQ")
    assert float(f[0]["value_double"]) == pytest.approx(float(b[0]["value_double"]) * 10, abs=0.01)
    log = json.loads((out / "faults.json").read_text(encoding="utf-8"))["data_faults"]
    assert {e["kind"] for e in log} == {"INTERRUPTION", "DUPLICATE", "UNIT_SCALE"}


def test_config_rejects_lubrication_that_resets_wear():
    bad = DEMO | {
        "maintenance": [{"component_id": "M01-BS1", "at_h": 10, "type": "LUBRICATION", "wear_delta": -0.1}]
    }
    with pytest.raises(ValidationError):
        SimulationConfig.model_validate(bad)


def test_config_rejects_non_simulated_device_ids():
    machines = json.loads(json.dumps(DEMO["machines"]))
    machines[0]["device_id"] = "E330331100001"
    with pytest.raises(ValidationError):
        SimulationConfig.model_validate(DEMO | {"machines": machines})


# --- simulated adapter implements the L1 contract ---------------------------------------------


def test_adapter_contract(demo_dir):
    a = SimulatedAdapter(demo_dir)
    assert isinstance(a, TimeSeriesAdapter) and a.is_simulated
    meta = a.discover()
    assert meta.is_simulated and {d.device_id for d in meta.devices} == {"SIM-M01", "SIM-M02"}
    assert meta.earliest_ts is not None and meta.latest_ts is not None
    window = TimeWindow(start=meta.earliest_ts, end=meta.earliest_ts + timedelta(hours=12))
    got = a.query_range("SIM-M01", "M01_BS1_SPD", window, limit=100_000)
    assert got and all(window.start <= r.ts < window.end for r in got)
    assert [r.ts for r in got] == sorted(r.ts for r in got)
    assert len(a.query_range("SIM-M01", "M01_BS1_SPD", window, limit=5)) == 5
    inc = a.query_incremental("SIM-M01", "M01_BS1_SPD", got[-1].ts, limit=10)
    assert inc and all(r.ts > got[-1].ts for r in inc)
    assert a.query_range("SIM-M01", "NO_SUCH_KEY", window, limit=10) == []
