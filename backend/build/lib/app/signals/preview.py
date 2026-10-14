"""Signal preview: full-resolution normalized series and chart series, returned separately (L2-06).

Data is read through each source's read-only adapter with bounded rows and time range (L1-06); no
SQL text is involved.
"""

from __future__ import annotations

from datetime import timedelta

from app.datasource.query_service.sources import DataSourceRegistry
from app.datasource.sql import QueryLimitError
from app.signals.downsample import visualization_series
from app.signals.normalize import normalize
from app.signals.schemas import (
    NormalizedSeries,
    PreviewRequest,
    PreviewResponse,
    SignalConfig,
    SignalDefinition,
)

PREVIEW_MAX_RANGE = timedelta(hours=168)
PREVIEW_MAX_ROWS = 100_000  # per signal; the source's own max_rows applies when lower


class UnknownSignalError(LookupError):
    pass


class PreviewError(ValueError):
    pass


def preview(sources: DataSourceRegistry, config: SignalConfig, req: PreviewRequest) -> PreviewResponse:
    if req.window.end - req.window.start > PREVIEW_MAX_RANGE:
        raise QueryLimitError(f"preview range exceeds {PREVIEW_MAX_RANGE.total_seconds() / 3600:g} h")
    given = {s.signal_id: s for s in req.signals}
    saved = {s.signal_id: s for s in config.signals}
    normalized: list[NormalizedSeries] = []
    charts = []
    simulated = False
    for m in req.mappings:
        signal: SignalDefinition | None = given.get(m.signal_id) or saved.get(m.signal_id)
        if signal is None:
            raise UnknownSignalError(f"signal '{m.signal_id}' is neither in the request nor configured")
        if m.conversion and m.conversion.target_unit != signal.unit:
            raise PreviewError(f"conversion for '{m.signal_id}' does not produce the signal's unit")
        adapter = sources.adapter(m.data_source_id)
        # one row beyond the limit tells whether the window holds more; stays within the source's max_rows
        limit = min(PREVIEW_MAX_ROWS, sources.config(m.data_source_id).max_rows - 1)
        rows = adapter.query_range(m.device_id, m.key_name, req.window, limit + 1)
        truncated = len(rows) > limit
        samples = normalize(rows[:limit], signal, m.conversion)
        is_sim = adapter.is_simulated
        simulated = simulated or is_sim
        if req.include_normalized:
            normalized.append(
                NormalizedSeries(
                    signal_id=signal.signal_id, unit=signal.unit, samples=samples, truncated=truncated
                )
            )
        charts.append(visualization_series(signal.signal_id, signal.unit, samples, req.max_points, is_sim))
    return PreviewResponse(
        window=req.window, normalized=normalized, visualization=charts, is_simulated=simulated
    )
