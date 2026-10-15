"""Online processing of a machine's data source into features and alarms (D-042).

The same steps the demo replay runs, for any machine whose signals are mapped to a registered source:
the regime catalog is learned from the first ``catalog_days`` after the first installation, then the
data after the newest stored feature window is read in steps, closed observation windows become
feature vectors, and the alarms are synced from the rules and the verified healthy references. It
stores no health state. Running it again with no new data changes nothing; a window that is still
open is left for the next run. Components without a verified reference get features but no verdict.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.schemas import ContractModel, TimeWindow
from app.core.security import Principal, Role
from app.datasource.query_service.sources import DataSourceRegistry
from app.decision.fleet import FleetHealthService
from app.equipment.lifecycle import EquipmentStore
from app.equipment.maintenance import MaintenanceService
from app.equipment.regimes import learn_catalog
from app.equipment.schemas import ImpactConfig
from app.equipment.state import load_series, observation_windows
from app.monitoring.alarms.service import AlarmService
from app.monitoring.baselines.verified import BaselineService
from app.monitoring.features.extract import _truncate, closed_windows, extract_features
from app.monitoring.features.store import FeatureStore
from app.monitoring.rules.engine import evaluate
from app.signals.registry import SignalConfigStore

SYSTEM = Principal(user_id="system:pipeline", role=Role.ENGINEER)
CATALOG_DAYS = 4.0
STEP_HOURS = 24.0
MAX_STEPS = 31
MIN_PROVISIONAL_DAYS = 1.0


class PipelineResult(ContractModel):
    machine_id: str
    processed_until: datetime | None
    windows_added: int
    windows_skipped: int
    catalog: str  # ready | pending | no_data | no_signals
    provisional: bool = False  # the regime catalog was learned from less than CATALOG_DAYS of data
    ready_at: datetime | None = None  # catalog "pending": when the full learning period is complete
    no_reference: list[str]
    alarms_raised: int
    is_simulated: bool


def _result(machine_id: str, catalog: str, **kw) -> PipelineResult:
    base = dict(processed_until=None, windows_added=0, windows_skipped=0, no_reference=[],
                alarms_raised=0, is_simulated=False)  # fmt: skip
    return PipelineResult(machine_id=machine_id, catalog=catalog, **(base | kw))


def run_machine(
    session: Session,
    sources: DataSourceRegistry,
    machine_id: str,
    until: datetime | None = None,
    catalog_days: float = CATALOG_DAYS,
    step_hours: float = STEP_HOURS,
    max_steps: int = MAX_STEPS,
    provisional: bool = False,
) -> PipelineResult:
    """``provisional`` lets a component that is younger than the learning period start anyway: the regime
    catalog is then learned from the first half of the data it has (at least one day of it), and the
    result says so. The catalog should be re-learned once the full period has passed."""
    until = until or datetime.now(UTC)
    equipment, features = EquipmentStore(session), FeatureStore(session)
    comps = {c.component_id: c for c in equipment.components(machine_id)}
    cfg = SignalConfigStore(session).current().content
    defs = {s.signal_id: s for s in cfg.signals}
    known = {c.data_source_id for c in sources.configs()}
    items = [
        (m, defs[m.signal_id])
        for m in cfg.mappings
        if m.component_id in comps and m.signal_id in defs and m.data_source_id in known
    ]
    lifecycles = {cid: equipment.lifecycles(cid) for cid in comps}
    installs = [lc.installed_at for lcs in lifecycles.values() for lc in lcs]
    if not items or not installs:
        return _result(machine_id, "no_signals")

    first = min(installs)
    short = False
    if provisional and until < first + timedelta(days=catalog_days):
        have = (until - first).total_seconds() / 86400
        if have >= MIN_PROVISIONAL_DAYS:
            catalog_days, short = have / 2, True
    cat_end = first + timedelta(days=catalog_days)
    if until < cat_end:
        return _result(machine_id, "pending", ready_at=cat_end)
    catalog_series = load_series(sources, items, TimeWindow(start=min(installs), end=cat_end))
    sim = any(s.is_simulated for s in catalog_series)
    catalog = learn_catalog(
        catalog_series, machine_id, TimeWindow(start=min(installs), end=cat_end), f"{machine_id}-online"
    )
    if not catalog.regimes:
        return _result(machine_id, "no_data", is_simulated=sim)

    types = {cid: c.type for cid, c in comps.items()}
    lc_entries = {
        cid: [(lc.lifecycle_id, lc.installed_at, lc.retired_at) for lc in lcs]
        for cid, lcs in lifecycles.items()
    }
    stab = timedelta(hours=ImpactConfig().stabilization_hours)
    maintenance = [
        (e.performed_at, e.performed_at + stab, e.event_id)
        for cid in comps
        for e in MaintenanceService(session).events(cid)
    ]
    last = [v.window.end for cid in comps for v in features.vectors(cid)]
    cursor = max([cat_end, *last])
    features.register_all()
    added = skipped = 0
    for _ in range(max_steps):
        if cursor >= until:
            break
        end = min(cursor + timedelta(hours=step_hours), until)
        window = TimeWindow(start=cursor, end=end)
        series = load_series(sources, items, window)
        ex = extract_features(
            series, window, types, lifecycles=lc_entries, catalog=catalog, maintenance=maintenance
        )
        added += features.save(ex.vectors, now=end)
        skipped += len(ex.skipped)
        # resume at the start of a window still open at ``end`` so it is not lost to the next step
        cut = end.timestamp()
        trimmed = _truncate(series, cut)
        wins, closed = observation_windows(trimmed), closed_windows(trimmed, cut)
        nxt = datetime.fromtimestamp(wins[-1][0], UTC) if len(wins) > len(closed) else end
        if nxt <= cursor:  # one window longer than a step: wait for it to close
            break
        cursor = nxt
        sim = sim or ex.is_simulated

    fleet = FleetHealthService(session)
    baselines, evals, missing = BaselineService(session), [], []
    limits = equipment.torque_limits()
    for cid in comps:
        vectors = features.vectors(cid)
        refs = {}
        for lc, ref_name in sorted({(v.lifecycle_id, v.feature_ref) for v in vectors}):
            if (ref := baselines.verified(cid, lc, ref_name)) is not None:
                refs[lc] = ref
        active = next((lc for lc in lifecycles[cid] if lc.status.value == "ACTIVE"), None)
        if vectors and active and active.lifecycle_id not in refs:
            missing.append(cid)
        evals += evaluate(vectors, refs, fleet.config.rules, fleet.settings.disabled(), limits=limits,
                          rules_version=fleet.rules_version())  # fmt: skip
    raised, _ = AlarmService(session).sync(evals, SYSTEM)
    newest = [v.window.end for cid in comps for v in features.vectors(cid)]
    return _result(
        machine_id,
        "ready",
        provisional=short,
        processed_until=max(newest) if newest else None,
        windows_added=added,
        windows_skipped=skipped,
        no_reference=sorted(missing),
        alarms_raised=len(raised),
        is_simulated=sim,
    )


def run_all(
    session: Session, sources: DataSourceRegistry, until: datetime | None = None
) -> list[PipelineResult]:
    out = []
    for m in EquipmentStore(session).machines():
        if m.is_simulated:  # simulated data is static; run those machines on request only
            continue
        try:
            out.append(run_machine(session, sources, m.machine_id, until))
            session.commit()
        except Exception:  # noqa: BLE001  (one machine's bad data must not stop the others)
            session.rollback()
            logging.getLogger(__name__).exception("pipeline failed for %s", m.machine_id)
    return out
