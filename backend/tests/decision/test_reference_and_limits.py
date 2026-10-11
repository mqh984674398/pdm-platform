"""D-040/D-041: reference quality warnings and the configured torque limit."""

from app.core.security import Principal, Role
from app.decision.schemas import HealthState as H
from app.equipment.lifecycle import EquipmentStore
from app.monitoring.baselines.verified import BaselineService

ADMIN = Principal(user_id="test-admin", role=Role.ADMIN)


def refs(svc, cid):
    return BaselineService(svc.session).baselines(cid)


def test_reference_taken_while_drifting_is_flagged(replay):
    svc, _ = replay
    (bad,) = [b for b in refs(svc, "A03-BS1") if b.kind.value == "VERIFIED_HEALTHY"][:1]
    assert any("drifts" in w.en for w in bad.warnings)  # S03: friction already creeping in the reference
    clean = [b for b in refs(svc, "A01-BS1") if b.kind.value == "VERIFIED_HEALTHY"]
    assert clean and not any("drifts" in w.en for w in clean[0].warnings)


def test_torque_safety_rule_runs_only_with_a_configured_limit(replay):
    svc, _ = replay
    eq = EquipmentStore(svc.session)
    before = svc.report("A02-BS1").decision
    assert "SF-TORQUE-LIMIT" not in before.safety_constraints_applied
    comp = eq.component("A02-BS1")
    eq.put_component(comp.model_copy(update={"torque_limit": 1e-3}), ADMIN)  # far below any real torque
    assert eq.torque_limits() == {"A02-BS1": 1e-3}
    after = FleetHealth(svc).report("A02-BS1").decision
    assert after.health_state == H.CRITICAL and "SF-TORQUE-LIMIT" in after.safety_constraints_applied


def FleetHealth(svc):  # a fresh service sees the new limit
    return type(svc)(svc.session)
