"""Dense SIMULATED dataset for chart performance checks (T019): one torque key at 1 s, gap-free.

Written in the simulator's raw telemetry format so the ordinary simulated adapter reads it. It has no
scenario, topology or ground truth and is used only to measure chart interaction on >= 1M points.
"""

from __future__ import annotations

import gzip
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

DEVICE, KEY = "SIM-BENCH", "BENCH_TORQUE"
START = datetime(2026, 1, 1, tzinfo=UTC)


def write_bench_dataset(directory: Path, rows: int = 1_100_000, seed: int = 7) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    t = START.timestamp() + np.arange(rows, dtype=float)
    v = 2.0 + 0.5 * np.sin(2 * np.pi * np.arange(rows) / 3600) + rng.normal(0, 0.05, rows)
    v[rows // 2 : rows // 2 + 5] += 3.0  # a short spike the downsampled chart must keep
    lines = ["deviceid,keyname,ts,datatype,value_double"]
    stamps = np.datetime_as_string(t.astype("datetime64[s]"), unit="s")
    lines += [f"{DEVICE},{KEY},{s}Z,double,{x:.4f}" for s, x in zip(stamps, v, strict=True)]
    path = directory / "raw_telemetry.csv.gz"
    path.write_bytes(gzip.compress(("\n".join(lines) + "\n").encode("utf-8"), compresslevel=1))
    return path
