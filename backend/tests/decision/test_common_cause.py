"""D-038: components on one shared drive chain that are abnormal together point to the chain (S19)."""

from app.decision.fleet import common_causes
from app.decision.schemas import HealthState as H


def test_two_abnormal_members_of_a_chain_share_one_cause():
    out = common_causes(
        [
            ("BS1", "DC1", H.WARNING),
            ("BS2", "DC1", H.CRITICAL),
            ("LM1", None, H.CRITICAL),
            ("BS3", "DC2", H.WARNING),
        ]
    )
    assert set(out) == {"BS1", "BS2"}
    assert out["BS1"].drive_chain_id == "DC1" and out["BS1"].component_ids == ["BS1", "BS2"]
    assert "DC1" in out["BS2"].note.zh and "drive chain" in out["BS2"].note.en


def test_one_abnormal_member_or_watch_level_is_not_a_common_cause():
    assert common_causes([("BS1", "DC1", H.WARNING), ("BS2", "DC1", H.WATCH)]) == {}
    assert common_causes([("BS1", "DC1", H.NORMAL), ("BS2", "DC1", H.NORMAL)]) == {}


def test_s19_shared_drive_chain_is_reported_on_the_fleet_and_component_report(replay):
    svc, machines = replay
    m = next(x for x in machines if x.scenario_id == "S19")
    fleet = next(x for x in svc.overview().machines if x.machine_id == m.machine_id)
    chained = [c for c in fleet.components if c.drive_chain_id]
    assert len(chained) == 2
    assert all(c.health in (H.WARNING, H.CRITICAL) for c in chained)
    assert all(c.common_cause and c.common_cause.drive_chain_id == chained[0].drive_chain_id for c in chained)
    report = svc.report(chained[0].component_id)
    assert report.common_cause is not None and len(report.common_cause.component_ids) == 2
    others = [c for x in svc.overview().machines if x.machine_id != m.machine_id for c in x.components]
    assert not any(c.common_cause for c in others)
