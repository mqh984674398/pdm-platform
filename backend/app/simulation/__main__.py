"""CLI: python -m app.simulation <config.json> [<config.json> ...] [--data-dir ../Data]

Generates each dataset into <data-dir>/simulated/<dataset_id>/ and updates <data-dir>/manifest.json.
"""

import argparse
import json
from pathlib import Path

from app.simulation.config import SimulationConfig
from app.simulation.generator import generate
from app.simulation.writer import update_manifest, write_dataset

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[3] / "Data"


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate simulated telemetry datasets (SIMULATED DATA).")
    ap.add_argument("configs", nargs="+", type=Path)
    ap.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    a = ap.parse_args()
    for path in a.configs:
        cfg = SimulationConfig.model_validate(json.loads(path.read_text(encoding="utf-8")))
        out = a.data_dir / "simulated" / cfg.dataset_id
        meta = write_dataset(generate(cfg), out)
        update_manifest(a.data_dir, meta, f"simulated/{cfg.dataset_id}")
        rows = meta["files"]["raw_telemetry.csv"]["rows"]  # type: ignore[index]
        print(f"{cfg.dataset_id}: {rows} raw rows -> {out}")


if __name__ == "__main__":
    main()
