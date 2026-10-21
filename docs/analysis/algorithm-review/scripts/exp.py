"""Replay experiments on the SIMULATED demo fleet: score algorithm variants against Golden Cases."""
import json, sys, tempfile, gzip, csv
from dataclasses import replace
from datetime import datetime
from pathlib import Path

BACKEND = Path("/home/claude/pdm-platform/backend")
DATA = BACKEND.parent / "Data"
sys.path.insert(0, str(BACKEND))

import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.main  # noqa
from app.core.db import Base
from app.datasource.query_service.sources import DataSourceRegistry
from app.simulation.demo_pipeline import add_demo_source, demo_machines, run_pipeline
from app.optimization.suite import demo_suite
from app.optimization.service import OptimizationService, _rank
from app.optimization import replay as replay_mod
from app.monitoring.rules import engine
from app.monitoring.rules.definitions import DEFAULT_RULES
from app.decision.aging import DEFAULT_POLICY
from app.decision import fusion
from app.decision.schemas import HealthState as H
from app.monitoring.baselines import stats as st

machines = demo_machines(DATA)
sources = DataSourceRegistry()
add_demo_source(sources, machines)
tmp = tempfile.mkdtemp()
eng = create_engine(f"sqlite:///{tmp}/x.db")
Base.metadata.create_all(eng)
s = Session(eng)
run_pipeline(s, sources, machines)
suite = demo_suite(s, DATA)
svc = OptimizationService(s, suite)
t0 = {c.component_id: c.t0 for c in suite.cases}


def score(rules=DEFAULT_RULES, policy=DEFAULT_POLICY, causal_ref=False, label=""):
    cases = []
    tot = dict(windows=0, within=0, over=0, under=0)
    first = {}
    for case in suite.cases:
        h = svc.histories[case.component_id]
        res = replay_mod.replay(h, rules, policy, svc.disabled)
        for r in res:
            hh = (r.decision.meta.data_window.start - case.t0).total_seconds() / 3600
            lvl = r.decision.health_state.value
            if causal_ref:
                ref = h.references.get(r.decision.lifecycle_id)
                if ref and r.decision.meta.data_window.end <= ref.verified_at:
                    lvl = "UNKNOWN"
            exp = next((e for e in case.expectations if e.start_h <= hh < e.end_h), None)
            k = case.component_id
            for thr in ("WATCH", "WARNING"):
                if _rank(lvl) >= _rank(thr) and (k, thr) not in first:
                    first[(k, thr)] = hh
            if exp is None:
                continue
            tot["windows"] += 1
            if lvl in exp.allowed:
                tot["within"] += 1
            elif _rank(lvl) > max(_rank(a) for a in exp.allowed):
                tot["over"] += 1
            else:
                tot["under"] += 1
    print(f"{label:<48} within {tot['within']}/{tot['windows']}  over {tot['over']}  under {tot['under']}")
    return tot, first


results = {}
results["baseline"] = score(label="baseline (current)")
results["causal_ref"] = score(causal_ref=True, label="baseline + windows before reference verification = UNKNOWN")

# robust deviation: median and (p95-p05)/3.29 as spread
orig_dev = engine.deviation
def robust_dev(value, ref):
    scale = max((ref.p95 - ref.p05) / 3.29 if ref.p95 is not None else ref.std, 0.01 * abs(ref.p50 or ref.mean), 1e-9)
    return (value - (ref.p50 if ref.p50 is not None else ref.mean)) / scale
engine.deviation = robust_dev
results["robust"] = score(label="robust deviation (median, P5-P95 spread)")
engine.deviation = orig_dev

# shrinkage of small-sample std: t-based inflation c = t_{0.975,n-1}/1.96
from scipy.stats import t as tdist
def small_n_dev(value, ref):
    n = max(ref.n or 2, 2)
    infl = tdist.ppf(0.975, n - 1) / 1.96
    return (value - ref.mean) / (st.spread(ref) * infl)
engine.deviation = small_n_dev
results["small_n"] = score(label="small-sample inflated spread (t-quantile)")
engine.deviation = orig_dev

# CUSUM variants
for k, h in ((1.0, 12.0), (1.0, 20.0), (2.0, 16.0), (3.0, 12.0)):
    r = DEFAULT_RULES.model_copy(update={"cusum_k": k, "cusum_h": h})
    results[f"cusum_{k}_{h}"] = score(rules=r, label=f"CUSUM k={k} h={h}")

# aging ceiling: aging cap does not apply once the hit is CRITICAL
orig_fuse = fusion.fuse
def fuse_ceiling(inp, policy=DEFAULT_POLICY):
    e = inp.evaluation
    if e is None:
        return orig_fuse(inp, policy)
    crit_rules = {h.rule_id for h in e.hits if h.level.value == "CRITICAL" and h.kind.value == "STATISTICAL"}
    res = orig_fuse(inp, policy)
    if crit_rules and res.decision.health_state != H.CRITICAL:
        d = res.decision.model_copy(update={"health_state": H.CRITICAL})
        res = fusion.FusionResult(d, res.evidence, res.recommendations, res.aging)
    return res
replay_mod.fuse = fuse_ceiling
results["aging_ceiling"] = score(label="aging grading never caps a CRITICAL hit")
replay_mod.fuse = orig_fuse

json.dump({k: {"tot": v[0], "first": {f"{a}|{b}": t for (a, b), t in v[1].items()}} for k, v in results.items()},
          open(sys.argv[1], "w"), indent=1)
