"""Champion/challenger evaluation on historical replay and the regression suite (T025, OPT-04).

The champion is the decision configuration in force (registry champion, or the shipped defaults).
Each candidate is replayed over the stored feature history of every suite component and scored
window by window against the expectations.
The run only recommends; promotion (with approval and rollback) belongs to the model registry (T026).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core import audit
from app.core.security import Principal
from app.decision.aging import AgingPolicy
from app.decision.config import active
from app.decision.schemas import HealthState
from app.equipment.lifecycle import EquipmentStore
from app.monitoring.baselines.verified import BaselineService
from app.monitoring.features.store import FeatureStore
from app.monitoring.rules.settings import RuleSettings
from app.monitoring.schemas import RuleSet
from app.optimization.candidates import Candidate, check_safety, generate
from app.optimization.replay import ComponentHistory, replay
from app.optimization.schemas import CandidateResult, CaseScore, OptimizationRun, ReplayMetrics
from app.optimization.suite import RegressionSuite

ORDER = [HealthState.NORMAL, HealthState.WATCH, HealthState.WARNING, HealthState.CRITICAL]
_LATEST: dict[str, OptimizationRun] = {}


class NoSuiteError(LookupError):
    pass


class NoRunError(LookupError):
    pass


def _rank(s: str) -> int:
    return ORDER.index(HealthState(s)) if s != "UNKNOWN" else -1


class OptimizationService:
    def __init__(self, session: Session, suite: RegressionSuite):
        if not suite.cases:
            raise NoSuiteError("no regression suite (Golden Cases) for the registered components")
        self.session, self.suite = session, suite
        eq, fs, bl = EquipmentStore(session), FeatureStore(session), BaselineService(session)
        self.disabled = RuleSettings(session).disabled()
        self.histories: dict[str, ComponentHistory] = {}
        for cid in {c.component_id for c in suite.cases}:
            comp = eq.component(cid)
            vectors = tuple(fs.vectors(cid))
            refs = {}
            for lc, ref_name in sorted({(v.lifecycle_id, v.feature_ref) for v in vectors}):
                ref = bl.verified(cid, lc, ref_name)
                if ref is not None:
                    refs[lc] = ref
            lcs = {lc.lifecycle_id: lc for lc in eq.lifecycles(cid)}
            self.histories[cid] = ComponentHistory(cid, comp.type, vectors, refs, lcs, eq.is_simulated(cid))

    def score(self, rules: RuleSet, policy: AgingPolicy) -> ReplayMetrics:
        cases = []
        decided = {cid: replay(h, rules, policy, self.disabled) for cid, h in self.histories.items()}
        for case in self.suite.cases:
            within = over = under = n = 0
            for r in decided[case.component_id]:
                h = (r.decision.meta.data_window.start - case.t0).total_seconds() / 3600
                exp = next((e for e in case.expectations if e.start_h <= h < e.end_h), None)
                if exp is None:
                    continue
                n += 1
                lvl = r.decision.health_state.value
                if lvl in exp.allowed:
                    within += 1
                elif _rank(lvl) > max(_rank(a) for a in exp.allowed):
                    over += 1
                else:
                    under += 1
            cases.append(
                CaseScore(
                    case_id=case.case_id,
                    component_id=case.component_id,
                    windows=n,
                    within=within,
                    over=over,
                    under=under,
                )
            )
        tot = sum(c.windows for c in cases)
        w = sum(c.within for c in cases)
        return ReplayMetrics(
            windows=tot,
            within=w,
            over=sum(c.over for c in cases),
            under=sum(c.under for c in cases),
            ratio=w / tot if tot else 0.0,
            cases=cases,
        )

    def _result(self, c: Candidate | None, champion: RuleSet, policy: AgingPolicy) -> CandidateResult:
        rules, pol = (c.rules, c.policy) if c else (champion, policy)
        check_safety(champion, rules)
        return CandidateResult(
            candidate_id=c.candidate_id if c else "champion",
            path=c.path if c else "champion",
            changes=c.changes if c else {},
            rules_version=rules.ref,
            policy_version=pol.version,
            safety_unchanged=True,
            metrics=self.score(rules, pol),
        )

    def run(self, who: Principal, n: int = 12, seed: int = 0) -> OptimizationRun:
        cfg = active(self.session)
        champion, policy = cfg.rules, cfg.policy
        base = self._result(None, champion, policy)
        results = [self._result(c, champion, policy) for c in generate(champion, policy, n, seed)]
        better = [
            r
            for r in results
            if r.metrics.within > base.metrics.within and r.metrics.under <= base.metrics.under
        ]
        best = max(better, key=lambda r: (r.metrics.within, -r.metrics.over), default=None)
        started = datetime.now(UTC)
        run = OptimizationRun(
            run_id=f"OPT-{started:%Y%m%dT%H%M%S}-{seed}",
            started_by=who.user_id,
            started_at=started,
            seed=seed,
            suite=self.suite.name,
            champion=base,
            candidates=results,
            recommended=best.candidate_id if best else None,
            is_simulated=self.suite.is_simulated,
        )
        audit.record(
            self.session,
            who,
            "optimization.run",
            "optimization",
            run.run_id,
            candidates=len(results),
            recommended=run.recommended,
            champion_ratio=base.metrics.ratio,
        )
        self.session.commit()
        _LATEST["run"] = run
        return run


def latest() -> OptimizationRun:
    if "run" not in _LATEST:
        raise NoRunError("no optimization run yet")
    return _LATEST["run"]
