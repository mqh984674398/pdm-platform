"""T025: time-ordered replay without future leakage, bounded candidates, safety invariant, API."""

from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.main  # noqa: F401  (registers tables)
from app.core.db import Base, get_session
from app.datasource.query_service.sources import DataSourceRegistry
from app.decision.aging import DEFAULT_POLICY
from app.decision.fleet import FleetHealthService
from app.main import create_app
from app.monitoring.rules.definitions import DEFAULT_RULES
from app.monitoring.schemas import RuleKind
from app.optimization import service as opt_service
from app.optimization.candidates import PATH_A, SafetyChangeError, apply_a, check_safety, generate
from app.optimization.replay import replay
from app.optimization.service import OptimizationService
from app.optimization.suite import demo_suite
from app.simulation.demo_pipeline import DEMO_FLEET, add_demo_source, demo_machines, run_pipeline
from app.simulation.golden import DATA_DIR

from ..query_service.conftest import Client

SELECTED = ("A02", "A03", "A04")  # S04 torque drift, S03 normal aging, S07 cylinder slowdown


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    engine = create_engine(f"sqlite:///{tmp_path_factory.mktemp('replay') / 'app.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    machines = demo_machines(DATA_DIR, [r for r in DEMO_FLEET if r[0] in SELECTED])
    sources = DataSourceRegistry()
    add_demo_source(sources, machines)
    with factory() as s:
        run_pipeline(s, sources, machines)

    def session():
        with factory() as s:
            yield s

    application = create_app(sources=sources)
    application.dependency_overrides[get_session] = session
    with factory() as s:
        svc = OptimizationService(s, demo_suite(s, DATA_DIR))
    yield Client(application), factory, svc
    engine.dispose()


def _key(r):
    d = r.decision
    return d.decision_id, d.health_state, tuple(x.en for x in d.reasons)


def test_replay_is_time_ordered_and_matches_the_live_service(env):
    _, factory, svc = env
    h = svc.histories["A02-BS1"]
    out = replay(h)
    ends = [r.decision.meta.data_window.end for r in out]
    assert ends == sorted(ends) and len(out) > 50
    with factory() as s:
        live = FleetHealthService(s).window_decisions("A02-BS1")
    assert [_key(r) for r in out] == [_key(r) for r in live]


@pytest.mark.parametrize("cid", ["A02-BS1", "A03-BS1", "A04-CY1"])
def test_no_future_leakage_decisions_do_not_change_when_later_data_arrives(env, cid):
    _, _, svc = env
    h = svc.histories[cid]
    full = replay(h)
    for frac in (0.3, 0.6, 0.9):
        cut = full[int(len(full) * frac)].decision.meta.data_window.end
        part = replay(h, until=cut)
        assert part, cid
        assert [_key(r) for r in part] == [_key(r) for r in full if r.decision.meta.data_window.end <= cut]


def test_truncated_replay_never_sees_later_windows(env):
    _, _, svc = env
    h = svc.histories["A03-BS1"]
    cut = min(v.window.end for v in h.vectors) + timedelta(days=40)
    for r in replay(h, until=cut):
        assert r.decision.meta.data_window.end <= cut
        assert all(a.age_days <= 41 for a in r.aging.values())


def test_candidates_never_touch_safety_rules():
    cands = generate(DEFAULT_RULES, DEFAULT_POLICY, 16, seed=3)
    assert len(cands) == 16 and {c.path for c in cands} == {"A", "B"}
    safety = [r for r in DEFAULT_RULES.rules if r.kind == RuleKind.SAFETY]
    for c in cands:
        assert [r for r in c.rules.rules if r.kind == RuleKind.SAFETY] == safety
        assert set(c.changes) <= set(PATH_A) | {"aging_max_rate", "aging_min_age_days", "aging_max_step"}
    a = next(c for c in cands if c.path == "A" and c.changes["threshold_scale"] != 1.0)
    st = {r.rule_id: r for r in DEFAULT_RULES.rules}
    for r in a.rules.rules:
        if r.kind == RuleKind.STATISTICAL:
            assert r.warning == pytest.approx(st[r.rule_id].warning * a.changes["threshold_scale"])


def test_a_candidate_that_weakens_a_safety_rule_is_refused():
    rules = DEFAULT_RULES.model_copy(
        update={
            "rules": [
                r.model_copy(update={"critical": (r.critical or 1) * 10}) if r.kind == RuleKind.SAFETY else r
                for r in DEFAULT_RULES.rules
            ]
        }
    )
    with pytest.raises(SafetyChangeError):
        check_safety(DEFAULT_RULES, rules)
    dropped = DEFAULT_RULES.model_copy(
        update={"rules": [r for r in DEFAULT_RULES.rules if r.kind != RuleKind.SAFETY]}
    )
    with pytest.raises(SafetyChangeError):
        check_safety(DEFAULT_RULES, dropped)
    check_safety(DEFAULT_RULES, apply_a(DEFAULT_RULES, {"threshold_scale": 1.2}, "X"))


def test_champion_score_matches_the_golden_comparison(env):
    _, _, svc = env
    m = svc.score(DEFAULT_RULES, DEFAULT_POLICY)
    by = {c.case_id: c for c in m.cases}
    # S04 and S07 match every graded window; S03's only deviations are documented (first 60 days WATCH)
    assert by["GC-S04-01"].within == by["GC-S04-01"].windows > 0
    assert by["GC-S07-01"].within == by["GC-S07-01"].windows > 0
    assert by["GC-S03-01"].under == 0 and m.within + m.over + m.under == m.windows


def test_optimization_readiness_says_what_would_be_replayed(env):
    client, _, _ = env
    r = client.get("/api/optimization/readiness", role="viewer").json()
    assert r["can_run"] and r["cases"] > 0 and r["components"] > 0 and r["stored_windows"] > 0
    assert r["is_simulated"] and r["reason"] is None


def test_optimization_api_runs_champion_vs_candidates(env):
    client, _, _ = env
    opt_service._LATEST.clear()
    assert client.get("/api/optimization/runs/latest").status_code == 404
    assert client.post("/api/optimization/runs", {"candidates": 4, "seed": 1}).status_code == 403
    r = client.post("/api/optimization/runs", {"candidates": 4, "seed": 1}, role="engineer")
    assert r.status_code == 200, r.text
    run = r.json()
    assert run["is_simulated"] and len(run["candidates"]) == 4
    assert run["champion"]["candidate_id"] == "champion"
    assert all(c["safety_unchanged"] for c in run["candidates"])
    ch = run["champion"]["metrics"]
    if run["recommended"]:
        best = next(c for c in run["candidates"] if c["candidate_id"] == run["recommended"])
        assert best["metrics"]["within"] > ch["within"] and best["metrics"]["under"] <= ch["under"]
    assert client.get("/api/optimization/runs/latest").json()["run_id"] == run["run_id"]
    # the run only recommends: the live rule set is unchanged
    assert client.get("/api/fleet").json()["rules_version"].startswith("pdm-rules@1.0.0")
