"""Simulated L1 adapter reading raw IoT-style rows written by the simulator (L1-07)."""

from __future__ import annotations

import csv
import gzip
import io
from bisect import bisect_left, bisect_right
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from app.core.schemas import TimeWindow
from app.datasource.adapter import TimeSeriesAdapter
from app.datasource.schemas import (
    ColumnInfo,
    DeviceKeys,
    RawTelemetryRow,
    SourceMetadata,
    SourceSchema,
    TableInfo,
)

# Columns of the simulator's raw_telemetry.csv, described like a database table.
RAW_COLUMNS = [
    ("deviceid", "TEXT", False),
    ("keyname", "TEXT", False),
    ("ts", "TIMESTAMP WITH TIME ZONE", False),
    ("datatype", "TEXT", True),
    ("value_double", "DOUBLE PRECISION", True),
]


class SimulatedAdapter(TimeSeriesAdapter):
    """Read-only, in-memory view of one or more datasets' ``raw_telemetry.csv``.

    Rows are served in timestamp order. The file keeps the arrival order produced by fault injection
    (out-of-order rows, duplicates); queries sort by timestamp like ``ORDER BY ts`` in SQL, duplicates
    are preserved. Several datasets form one source when their device ids do not overlap.
    """

    is_simulated = True

    def __init__(self, dataset_dir: Path | Sequence[Path], data_source_id: str = "simulated"):
        self.data_source_id = data_source_id
        self.dataset_dirs = [dataset_dir] if isinstance(dataset_dir, Path) else list(dataset_dir)
        rows: dict[tuple[str, str], list[tuple[datetime, float | None, int]]] = {}
        self._refs: dict[tuple[str, str], str] = {}
        for directory in self.dataset_dirs:
            ref = f"{data_source_id}:{directory.name}"
            own: set[tuple[str, str]] = set()
            for seq, (device, key, ts, value) in enumerate(_read_rows(directory)):
                pair = (device, key)
                if pair not in own and pair in self._refs:
                    raise ValueError(f"device {device} appears in more than one dataset")
                own.add(pair)
                self._refs[pair] = ref
                rows.setdefault(pair, []).append((ts, value, seq))  # seq: line order in the file
        self._rows = {k: sorted(v, key=lambda x: x[0]) for k, v in rows.items()}
        self._ts = {k: [t for t, _, _ in v] for k, v in self._rows.items()}

    def row_counts(self) -> dict[tuple[str, str], int]:
        """Stored rows per (device, key), duplicates included."""
        return {k: len(v) for k, v in self._rows.items()}

    def discover(self) -> SourceMetadata:
        devices: dict[str, list[str]] = {}
        for device, key in sorted(self._rows):
            devices.setdefault(device, []).append(key)
        all_ts = [ts for series in self._ts.values() for ts in (series[0], series[-1]) if series]
        return SourceMetadata(
            data_source_id=self.data_source_id,
            devices=[DeviceKeys(device_id=d, key_names=k) for d, k in devices.items()],
            earliest_ts=min(all_ts) if all_ts else None,
            latest_ts=max(all_ts) if all_ts else None,
            is_simulated=True,
        )

    def inspect_schema(self) -> SourceSchema:
        return SourceSchema(
            data_source_id=self.data_source_id,
            engine="simulated",
            tables=[
                TableInfo(
                    schema_name=None,
                    name="raw_telemetry",
                    columns=[ColumnInfo(name=n, type=t, nullable=null) for n, t, null in RAW_COLUMNS],
                )
            ],
            is_simulated=True,
        )

    def query_range(
        self, device_id: str, key_name: str, window: TimeWindow, limit: int
    ) -> list[RawTelemetryRow]:
        ts = self._ts.get((device_id, key_name), [])
        lo, hi = bisect_left(ts, window.start), bisect_left(ts, window.end)
        return self._slice(device_id, key_name, lo, min(hi, lo + limit))

    def query_incremental(
        self, device_id: str, key_name: str, since: datetime, limit: int
    ) -> list[RawTelemetryRow]:
        ts = self._ts.get((device_id, key_name), [])
        lo = bisect_right(ts, since)
        return self._slice(device_id, key_name, lo, min(len(ts), lo + limit))

    def _slice(self, device_id: str, key_name: str, lo: int, hi: int) -> list[RawTelemetryRow]:
        return [
            RawTelemetryRow(
                device_id=device_id,
                key_name=key_name,
                ts=t,
                value=v,
                source_ref=self._refs[(device_id, key_name)],
                is_simulated=True,
                arrival_seq=seq,
            )
            for t, v, seq in self._rows.get((device_id, key_name), [])[lo:hi]
        ]


def _read_rows(dataset_dir: Path):
    path = dataset_dir / "raw_telemetry.csv"
    if path.exists():
        text = path.read_text(encoding="utf-8")
    else:
        text = gzip.decompress((dataset_dir / "raw_telemetry.csv.gz").read_bytes()).decode("utf-8")
    with io.StringIO(text, newline="") as fh:
        for r in csv.DictReader(fh):
            ts = datetime.fromisoformat(r["ts"].replace("Z", "+00:00"))
            value = float(r["value_double"]) if r["value_double"] else None
            yield r["deviceid"], r["keyname"], ts, value
