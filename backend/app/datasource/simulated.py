"""Simulated L1 adapter reading raw IoT-style rows written by the simulator (L1-07)."""

from __future__ import annotations

import csv
import gzip
import io
from bisect import bisect_left, bisect_right
from datetime import datetime
from pathlib import Path

from app.core.schemas import TimeWindow
from app.datasource.adapter import TimeSeriesAdapter
from app.datasource.schemas import DeviceKeys, RawTelemetryRow, SourceMetadata


class SimulatedAdapter(TimeSeriesAdapter):
    """Read-only, in-memory view of ``raw_telemetry.csv``. Rows are served in timestamp order.

    The file keeps the arrival order produced by fault injection (out-of-order rows, duplicates);
    queries sort by timestamp like ``ORDER BY ts`` in SQL, duplicates are preserved.
    """

    is_simulated = True

    def __init__(self, dataset_dir: Path, data_source_id: str = "simulated"):
        self.data_source_id = data_source_id
        self._source_ref = f"{data_source_id}:{dataset_dir.name}"
        rows: dict[tuple[str, str], list[tuple[datetime, float | None]]] = {}
        path = dataset_dir / "raw_telemetry.csv"
        if path.exists():
            text = path.read_text(encoding="utf-8")
        else:
            text = gzip.decompress((dataset_dir / "raw_telemetry.csv.gz").read_bytes()).decode("utf-8")
        with io.StringIO(text, newline="") as fh:
            for r in csv.DictReader(fh):
                ts = datetime.fromisoformat(r["ts"].replace("Z", "+00:00"))
                value = float(r["value_double"]) if r["value_double"] else None
                rows.setdefault((r["deviceid"], r["keyname"]), []).append((ts, value))
        self._rows = {k: sorted(v, key=lambda x: x[0]) for k, v in rows.items()}
        self._ts = {k: [t for t, _ in v] for k, v in self._rows.items()}

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
                source_ref=self._source_ref,
                is_simulated=True,
            )
            for t, v in self._rows.get((device_id, key_name), [])[lo:hi]
        ]
