"""Write a SimulationResult to Data/simulated/<dataset_id>/ and register it in Data/manifest.json.

Output is byte-identical for identical configs: no wall-clock timestamps, fixed float formatting,
stable ordering, LF line endings.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from datetime import UTC
from pathlib import Path

import numpy as np

from app.simulation.generator import GENERATOR_VERSION, SimulationResult

NOTICE = {
    "zh": "模拟数据：由确定性生成器产生，仅用于开发、测试和演示，不代表真实工业设备的行为或预测结果。",
    "en": "SIMULATED DATA: produced by a deterministic generator for development, tests, and demos only. "
    "It does not represent real industrial equipment behavior or prediction results.",
}
TRUTH_COLUMNS = ["friction_factor", "ripple_fraction", "release_factor", "extend_factor", "retract_factor"]


def _iso(start: np.datetime64, seconds: np.ndarray) -> np.ndarray:
    ms = np.round(seconds * 1000).astype("int64").astype("timedelta64[ms]")
    return np.char.add(np.datetime_as_string(start + ms, unit="ms"), "Z")


def _dump_json(obj: object) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


PLANT_FIELDS = {"process_id", "device_id", "path"}


def _models(items) -> list[dict]:
    # torque_limit is plant configuration (D-041), not part of a simulated scenario's topology
    skip = {"torque_limit"}
    return [i.model_dump(mode="json", exclude=skip & set(type(i).model_fields)) for i in items]


def config_hash(result: SimulationResult) -> str:
    canonical = json.dumps(result.config.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def write_dataset(result: SimulationResult, out_dir: Path, compress_csv: bool = False) -> dict[str, object]:
    """Write all dataset files. With ``compress_csv`` CSV files are written as deterministic ``.csv.gz``;
    recorded checksums always refer to the uncompressed content, so they are independent of zlib builds.
    """
    cfg = result.config
    out_dir.mkdir(parents=True, exist_ok=True)
    start = np.datetime64(_utc_naive(cfg), "ms")
    files: dict[str, dict[str, object]] = {}

    conv = {(mp.device_id, mp.key_name): mp for mp in result.mappings}
    raw_lines = ["deviceid,keyname,ts,datatype,value_double"]
    norm_lines = ["signal_id,ts,value,unit,quality,source_ref,is_simulated"]
    for (device, key), (t, v) in sorted(result.raw.items()):
        if t.size == 0:
            continue
        ts = _iso(start, t)
        mp = conv[(device, key)]
        assert mp.conversion is not None
        v = np.round(v, 3)  # normalized values derive from the raw values exactly as written
        nv = v * mp.conversion.scale + mp.conversion.offset
        src = f"{mp.data_source_id}:{mp.template_id}@1"
        for stamp, rv, n in zip(ts, v, nv, strict=True):
            raw_lines.append(f"{device},{key},{stamp},Double,{rv:.3f}")
            norm_lines.append(f"{mp.signal_id},{stamp},{n:.9g},{mp.conversion.target_unit},,{src},true")
    _write(out_dir / "raw_telemetry.csv", raw_lines, files, compress_csv)
    _write(out_dir / "normalized.csv", norm_lines, files, compress_csv)

    w_lines = ["machine_id,window_index,window_start,window_end,state,recipe_id"]
    for w in result.windows:
        s, e = _iso(start, np.array([w.start_h * 3600, w.end_h * 3600]))
        w_lines.append(f"{w.machine_id},{w.index},{s},{e},{w.state.value},{w.recipe_id}")
    _write(out_dir / "truth_windows.csv", w_lines, files, compress_csv)

    c_lines = [
        "window_start,machine_id,component_id,lifecycle_id,state,recipe_id,wear," + ",".join(TRUTH_COLUMNS)
    ]
    for row in result.component_truth:
        (s,) = _iso(start, np.array([float(row["window_start_h"]) * 3600]))
        vals = ",".join("" if c not in row else f"{row[c]:.6f}" for c in TRUTH_COLUMNS)
        c_lines.append(
            f"{s},{row['machine_id']},{row['component_id']},{row['lifecycle_id']},{row['state']},"
            f"{row['recipe_id']},{row['wear']:.6f},{vals}"
        )
    _write(out_dir / "truth_components.csv", c_lines, files, compress_csv)

    _write_text(
        out_dir / "topology.json",
        _dump_json(
            {
                "is_simulated": True,
                "machines": [  # plant placement (D-037) is configured per installation, not part of datasets
                    {k: v for k, v in m.items() if k not in PLANT_FIELDS} for m in _models(result.machines)
                ],
                "components": _models(result.components),
                # the simulator does not track usage periods (T014 field), so stored datasets stay unchanged
                "lifecycles": [
                    lc.model_dump(mode="json", exclude={"usage_counted_until"}) for lc in result.lifecycles
                ],
                "signals": _models(result.signals),
                "mappings": _models(result.mappings),
            }
        ),
        files,
    )
    _write_text(out_dir / "maintenance_events.json", _dump_json(_models(result.maintenance_events)), files)
    _write_text(
        out_dir / "faults.json",
        _dump_json(
            {
                "data_faults": result.fault_log,
                "incomplete_operations": result.incomplete_log,
            }
        ),
        files,
    )
    _write_text(out_dir / "config.json", _dump_json(cfg.model_dump(mode="json")), files)

    meta = {
        "dataset_id": cfg.dataset_id,
        "description": cfg.description,
        "is_simulated": True,
        "notice": NOTICE,
        "generator_version": GENERATOR_VERSION,
        "seed": cfg.seed,
        "config_sha256": config_hash(result),
        "start": cfg.start.isoformat(),
        "duration_hours": cfg.duration_hours,
        "raw_format": "deviceid,keyname,ts,datatype,value_double",
        "raw_format_note": "IoT-style layout; the real source schema is unverified (L1-08)",
        "files": files,
    }
    _write_text(out_dir / "dataset.json", _dump_json(meta), {})
    return meta


def _utc_naive(cfg) -> str:
    return cfg.start.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S")


def _write(path: Path, lines: list[str], files: dict, compress: bool = False) -> None:
    _write_text(path, "\n".join(lines) + "\n", files, rows=len(lines) - 1, compress=compress)


def _write_text(path: Path, text: str, files: dict, rows: int | None = None, compress: bool = False) -> None:
    data = text.encode("utf-8")
    if compress:
        stale = path
        path = path.with_name(path.name + ".gz")
        path.write_bytes(gzip.compress(data, compresslevel=9, mtime=0))
        stale.unlink(missing_ok=True)
    else:
        path.write_bytes(data)
        path.with_name(path.name + ".gz").unlink(missing_ok=True)
    entry: dict[str, object] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    if rows is not None:
        entry["rows"] = rows
    if compress:
        entry["gzip"] = True
    files[path.name] = entry


def read_text(path: Path) -> str:
    """Read a dataset file, transparently handling the ``.gz`` variant."""
    gz = path.with_name(path.name + ".gz")
    if not path.exists() and gz.exists():
        return gzip.decompress(gz.read_bytes()).decode("utf-8")
    return path.read_text(encoding="utf-8")


def update_manifest(data_dir: Path, meta: dict[str, object], rel_path: str) -> None:
    """Register a dataset in Data/manifest.json (sorted, deterministic)."""
    manifest_path = data_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    manifest.setdefault("is_simulated_workspace", True)
    manifest.setdefault("notice", NOTICE)
    datasets = {d["dataset_id"]: d for d in manifest.get("datasets", [])}
    datasets[str(meta["dataset_id"])] = {
        "dataset_id": meta["dataset_id"],
        "path": rel_path,
        "is_simulated": True,
        "generator_version": meta["generator_version"],
        "seed": meta["seed"],
        "config_sha256": meta["config_sha256"],
        "files": meta["files"],
    }
    manifest["datasets"] = [datasets[k] for k in sorted(datasets)]
    manifest_path.write_bytes(_dump_json(manifest).encode("utf-8"))
