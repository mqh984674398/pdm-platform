"""Candidates for the deployment registry (T026): decision configurations (Path A/B) and models (Path C).

Each proposal is evaluated before it is stored:

- decision-config: the candidate and the champion in force are both replayed over the stored history
  and scored on the Golden Case suite. The gate passes when the candidate has at least as many windows
  within expectation, no more windows below expectation, and identical safety rules.
- component-model:<TYPE>: a model from the trained-model registry (T022). Its training must come from
  recorded truth (simulator ground truth or documented failures), never from health states or online
  observations; its lifecycle-grouped validation must exist, reach ROC AUC 0.8, and not fall below the
  champion model's F1.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.registry import DeploymentRegistry, DeploymentVersion, RegistryError
from app.core.security import Principal, Role
from app.decision.config import KIND, DecisionConfig, active, from_payload
from app.optimization.candidates import SafetyChangeError, apply_a, apply_b, check_safety
from app.optimization.schemas import OptimizationRun, ReplayMetrics
from app.optimization.service import OptimizationService
from app.optimization.suite import RegressionSuite
from app.prediction.models.registry import ModelRecord

SYSTEM = Principal(user_id="system:registry", role=Role.ADMIN)
MIN_AUC = 0.8
TRUTH_PREFIXES = ("SIMULATED truth", "Recorded failure")


def ensure_champion(session: Session, simulated: bool) -> DeploymentVersion:
    reg = DeploymentRegistry(session, KIND)
    return reg.champion() or reg.seed(active(session).payload(), SYSTEM, simulated)


def _summary(m: ReplayMetrics) -> dict[str, Any]:
    return {"windows": m.windows, "within": m.within, "over": m.over, "under": m.under, "ratio": m.ratio}


def evaluate_config(session: Session, suite: RegressionSuite, cand: DecisionConfig) -> dict[str, Any]:
    champ_v = ensure_champion(session, suite.is_simulated)
    champ = from_payload(champ_v.payload, champ_v.version_id)
    svc = OptimizationService(session, suite)
    reasons = []
    try:
        check_safety(champ.rules, cand.rules)
        safety_ok = True
    except SafetyChangeError as e:
        safety_ok, reasons = False, [str(e)]
    a, b = svc.score(champ.rules, champ.policy), svc.score(cand.rules, cand.policy)
    if b.within < a.within:
        reasons.append(f"fewer windows within expectation ({b.within} < {a.within})")
    if b.under > a.under:
        reasons.append(f"more windows below expectation ({b.under} > {a.under})")
    return {
        "gate_passed": safety_ok and not reasons,
        "baseline_version": champ_v.version_id,
        "suite": suite.name,
        "champion": _summary(a),
        "candidate": _summary(b),
        "safety_unchanged": safety_ok,
        "reasons": reasons,
        "is_simulated": suite.is_simulated,
    }


def propose_from_run(
    session: Session,
    suite: RegressionSuite,
    run: OptimizationRun,
    candidate_id: str,
    who: Principal,
    comment: str,
) -> DeploymentVersion:
    c = next((x for x in run.candidates if x.candidate_id == candidate_id), None)
    if c is None:
        raise RegistryError(f"{candidate_id} is not in run {run.run_id}")
    base = from_payload(ensure_champion(session, suite.is_simulated).payload, None)
    tag = f"{run.run_id}-{candidate_id}"
    if c.path == "A":
        cand = DecisionConfig(apply_a(base.rules, c.changes, tag), base.policy, None)
    else:
        cand = DecisionConfig(base.rules, apply_b(base.policy, c.changes, tag), None)
    ev = evaluate_config(session, suite, cand) | {
        "source": {"run_id": run.run_id, "candidate_id": candidate_id, "changes": c.changes}
    }
    return DeploymentRegistry(session, KIND).propose(cand.payload(), ev, who, comment, suite.is_simulated)


def model_kind(rec: ModelRecord) -> str:
    return f"component-model:{rec.component_type.value}"


def check_training_sources(rec: ModelRecord) -> None:
    """Training labels must be recorded truth; health states and online observations never are (AC3)."""
    if not rec.label_definition.startswith(TRUTH_PREFIXES):
        raise RegistryError(f"{rec.model_id}: labels '{rec.label_definition[:60]}' are not recorded truth")
    for word in ("health", "ADAPTIVE", "online", "WATCH", "WARNING", "CRITICAL"):
        if word.lower() in rec.label_definition.lower():
            raise RegistryError(
                f"{rec.model_id}: labels refer to '{word}'; only recorded truth may label training"
            )


def propose_model(session: Session, rec: ModelRecord, who: Principal, comment: str) -> DeploymentVersion:
    check_training_sources(rec)
    reg = DeploymentRegistry(session, model_kind(rec))
    champ = reg.champion()
    cv = rec.metrics.get("grouped_cv") or {}
    reasons = []
    if not cv:
        reasons.append("no lifecycle-grouped validation recorded")
    elif (cv.get("roc_auc") or 0) < MIN_AUC:
        reasons.append(f"grouped-CV ROC AUC {cv.get('roc_auc')} below {MIN_AUC}")
    champ_f1 = (champ.payload.get("metrics", {}).get("grouped_cv") or {}).get("f1") if champ else None
    if champ_f1 is not None and (cv.get("f1") or 0) < champ_f1:
        reasons.append(f"grouped-CV F1 {cv.get('f1')} below the champion's {champ_f1}")
    ev = {
        "gate_passed": not reasons,
        "baseline_version": champ.version_id if champ else None,
        "grouped_cv": cv,
        "time_split": rec.metrics.get("time_split"),
        "reasons": reasons,
        "is_simulated": rec.is_simulated,
    }
    return reg.propose(rec.model_dump(mode="json"), ev, who, comment, rec.is_simulated)
