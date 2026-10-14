"""Quality report over configured or draft signals: reads full-resolution rows through the read-only
adapters (bounded), then runs the per-signal checks and the speed/torque pair checks."""

from __future__ import annotations

from datetime import timedelta

from app.core.schemas import TimeWindow
from app.datasource.query_service.sources import DataSourceRegistry
from app.datasource.sql import QueryLimitError
from app.monitoring.alignment.pairs import check_pair
from app.monitoring.quality.assess import Rows, assess
from app.monitoring.schemas import QualityRequest, QualityResponse, SignalPair
from app.signals.schemas import PhysicalQuantity, SignalConfig, SignalDefinition, SignalMapping

MAX_WINDOW = timedelta(hours=168)
MAX_ROWS = 200_000  # per signal and period; the source's own max_rows applies when lower


class UnknownQualitySignalError(LookupError):
    pass


class QualityRequestError(ValueError):
    pass


def _resolve(config: SignalConfig, req: QualityRequest) -> list[tuple[SignalMapping, SignalDefinition]]:
    given = {s.signal_id: s for s in req.signals}
    saved = {s.signal_id: s for s in config.signals}
    saved_maps = {m.signal_id: m for m in config.mappings}
    mappings = list(req.mappings)
    for sid in req.signal_ids:
        if sid not in saved_maps:
            raise UnknownQualitySignalError(f"signal '{sid}' has no saved mapping")
        mappings.append(saved_maps[sid])
    if not mappings:
        raise QualityRequestError("give signal_ids or mappings")
    out = []
    for m in mappings:
        signal = given.get(m.signal_id) or saved.get(m.signal_id)
        if signal is None:
            raise UnknownQualitySignalError(
                f"signal '{m.signal_id}' is neither in the request nor configured"
            )
        if m.conversion and m.conversion.target_unit != signal.unit:
            raise QualityRequestError(f"conversion for '{m.signal_id}' does not produce the signal's unit")
        out.append((m, signal))
    return out


def _read(sources: DataSourceRegistry, m: SignalMapping, window: TimeWindow) -> Rows:
    limit = min(MAX_ROWS, sources.config(m.data_source_id).max_rows)
    rows = sources.adapter(m.data_source_id).query_range(m.device_id, m.key_name, window, limit)
    if len(rows) >= limit:
        raise QueryLimitError(f"more than {limit} rows for '{m.signal_id}'; use a shorter window")
    return Rows.build(rows, m.conversion)


def _auto_pairs(items: list[tuple[SignalMapping, SignalDefinition]]) -> list[SignalPair]:
    by_component: dict[str, dict[PhysicalQuantity, str]] = {}
    for m, s in items:
        if m.component_id and s.quantity in (PhysicalQuantity.SPEED, PhysicalQuantity.TORQUE):
            by_component.setdefault(m.component_id, {}).setdefault(s.quantity, s.signal_id)
    return [
        SignalPair(speed_signal_id=q[PhysicalQuantity.SPEED], torque_signal_id=q[PhysicalQuantity.TORQUE])
        for q in by_component.values()
        if len(q) == 2
    ]


def quality_report(sources: DataSourceRegistry, config: SignalConfig, req: QualityRequest) -> QualityResponse:
    if req.window.end - req.window.start > MAX_WINDOW:
        raise QueryLimitError(f"quality window exceeds {MAX_WINDOW.total_seconds() / 3600:g} h")
    items = _resolve(config, req)
    lookback = (
        TimeWindow(start=req.window.start - timedelta(hours=req.lookback_hours), end=req.window.start)
        if req.lookback_hours > 0
        else None
    )
    data: dict[str, tuple[SignalDefinition, Rows, Rows | None]] = {}
    for m, s in items:
        rows = _read(sources, m, req.window)
        ref = _read(sources, m, lookback) if lookback else None
        data[s.signal_id] = (s, rows, ref)
    reports = [assess(s, rows, req.window, ref) for s, rows, ref in data.values()]

    alignment = []
    for p in req.pairs if req.pairs is not None else _auto_pairs(items):
        if p.speed_signal_id not in data or p.torque_signal_id not in data:
            raise QualityRequestError(f"pair {p.speed_signal_id}/{p.torque_signal_id} is not in this request")
        (spd, s_rows, s_ref), (_, t_rows, t_ref) = data[p.speed_signal_id], data[p.torque_signal_id]
        expected = spd.expected_sampling_s
        tolerance = req.tolerance_s or (0.5 * expected if expected else 1.0)
        reference = (s_ref, t_ref) if s_ref is not None and t_ref is not None else None
        alignment.append(check_pair(p.speed_signal_id, p.torque_signal_id, s_rows, t_rows, req.window,
                                    tolerance, expected, reference))  # fmt: skip
    simulated = any(r.is_simulated for r in reports) or any(
        sources.adapter(m.data_source_id).is_simulated for m, _ in items
    )
    return QualityResponse(window=req.window, reports=reports, alignment=alignment, is_simulated=simulated)
