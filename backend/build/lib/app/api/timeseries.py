"""Chart series and full-resolution export for saved signals (T019, L2-06, UI-06).

Rows come through the source's read-only adapter, bounded by the source's ``max_rows`` and at most
366 days. Chart series are downsampled on the server (min/max per bucket) and flagged as such; they
are for display only. The export returns every row at full resolution in signal units and is audited.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Annotated

import numpy as np
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import AwareDatetime
from sqlalchemy.orm import Session

from app.core.audit import record as audit
from app.core.db import get_session
from app.core.schemas import TimeWindow
from app.core.security import Principal, Role, require
from app.datasource.query_service.sources import DataSourceRegistry
from app.datasource.sql import QueryLimitError
from app.signals.downsample import minmax
from app.signals.preview import UnknownSignalError
from app.signals.registry import SignalConfigStore
from app.signals.schemas import SeriesPoint, VisualizationSeries

router = APIRouter(tags=["timeseries"])
DB = Annotated[Session, Depends(get_session)]
Viewer = Annotated[Principal, Depends(require(Role.VIEWER))]
MAX_RANGE = timedelta(days=366)


def _sources(request: Request) -> DataSourceRegistry:
    return request.app.state.sources


Sources = Annotated[DataSourceRegistry, Depends(_sources)]


def _read(db: Session, reg: DataSourceRegistry, signal_id: str, start: datetime, end: datetime):
    window = TimeWindow(start=start, end=end)
    if window.end - window.start > MAX_RANGE:
        raise QueryLimitError("chart range exceeds 366 days")
    content = SignalConfigStore(db).current().content
    signal = next((s for s in content.signals if s.signal_id == signal_id), None)
    mapping = next((m for m in content.mappings if m.signal_id == signal_id), None)
    if signal is None or mapping is None:
        raise UnknownSignalError(f"signal '{signal_id}' has no saved mapping")
    limit = reg.config(mapping.data_source_id).max_rows
    adapter = reg.adapter(mapping.data_source_id)
    t, v = adapter.query_arrays(mapping.device_id, mapping.key_name, window, limit + 1)
    if t.size > limit:
        raise QueryLimitError(f"more than {limit} rows in the range; zoom in or export a shorter period")
    if mapping.conversion is not None:
        v = v * mapping.conversion.scale + mapping.conversion.offset
    return signal, t, v, adapter.is_simulated


@router.get("/timeseries/{signal_id}", response_model=VisualizationSeries)
def chart_series(
    signal_id: str,
    start: AwareDatetime,
    end: AwareDatetime,
    _: Viewer,
    db: DB,
    reg: Sources,
    max_points: Annotated[int, Query(ge=100, le=5000)] = 1500,
) -> VisualizationSeries:
    signal, t, v, sim = _read(db, reg, signal_id, start, end)
    count = int(np.count_nonzero(~np.isnan(v)))
    tt, vv, down = minmax(t, v, max_points)
    points = [
        SeriesPoint(ts=datetime.fromtimestamp(a, UTC), value=None if np.isnan(b) else float(b))
        for a, b in zip(tt.tolist(), vv.tolist(), strict=True)
    ]
    return VisualizationSeries(
        signal_id=signal_id,
        unit=signal.unit,
        points=points,
        downsampled=down,
        source_point_count=count,
        method="minmax" if down else None,
        is_simulated=sim,
    )


@router.get("/timeseries/{signal_id}/extent", response_model=TimeWindow | None)
def series_extent(signal_id: str, _: Viewer, db: DB, reg: Sources) -> TimeWindow | None:
    """Earliest and latest timestamps of the signal's source, to set the chart's full range."""
    content = SignalConfigStore(db).current().content
    mapping = next((m for m in content.mappings if m.signal_id == signal_id), None)
    if mapping is None:
        raise UnknownSignalError(f"signal '{signal_id}' has no saved mapping")
    meta = reg.adapter(mapping.data_source_id).discover()
    if meta.earliest_ts is None or meta.latest_ts is None or meta.latest_ts <= meta.earliest_ts:
        return None
    return TimeWindow(start=meta.earliest_ts, end=meta.latest_ts + timedelta(seconds=1))


@router.get("/timeseries/{signal_id}/export")
def export_series(
    signal_id: str, start: AwareDatetime, end: AwareDatetime, who: Viewer, db: DB, reg: Sources
) -> StreamingResponse:
    signal, t, v, sim = _read(db, reg, signal_id, start, end)
    audit(db, who, "timeseries.export", "signal", signal_id, start=start.isoformat(), end=end.isoformat(),
          rows=int(t.size), is_simulated=sim)  # fmt: skip
    db.commit()

    def rows() -> Iterator[str]:
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(["ts", f"value_{signal.unit}", "is_simulated"])
        for i in range(0, t.size, 10_000):
            for a, b in zip(t[i : i + 10_000].tolist(), v[i : i + 10_000].tolist(), strict=True):
                ts = datetime.fromtimestamp(a, UTC).isoformat().replace("+00:00", "Z")
                w.writerow([ts, "" if b != b else repr(b), "true" if sim else "false"])
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate()

    name = f"{signal_id}_{start:%Y%m%dT%H%M}_{end:%Y%m%dT%H%M}{'_SIMULATED' if sim else ''}.csv"
    return StreamingResponse(
        rows(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}"'}
    )
