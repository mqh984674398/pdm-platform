"""T014 AC2: lubrication (S09/S10) and other non-replacing maintenance never reset aging (SIMULATED)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from ..equipment.conftest import scenario
from .conftest import iso, record, seed, sim_maintenance


@pytest.mark.parametrize("sid", ["S09", "S10", "S11"])
def test_maintenance_keeps_lifecycle_and_aging(client, sid):
    seed(client, sid)
    sc = scenario(sid)
    m = sim_maintenance(sid)[0]
    cid = m["component_id"]
    t = sc.t0 + timedelta(hours=m["at_h"])
    # operation before the event
    r = client.post(f"/api/components/{cid}/lifecycles", {"installed_at": iso(sc.t0)}, role="engineer")
    assert r.status_code == 409
    lc = client.get(f"/api/components/{cid}/lifecycles").json()[0]
    body = {"until": iso(t), "operating_hours": 2.0, "cycles": 100}
    assert (
        client.post(f"/api/lifecycles/{lc['lifecycle_id']}/usage", body, role="engineer").status_code == 200
    )
    before = client.get(f"/api/components/{cid}/aging", params={"at": iso(t)}).json()

    out = record(client, cid, m["type"], iso(t)).json()
    assert out["event"]["new_lifecycle_id"] is None
    assert [x["lifecycle_id"] for x in out["lifecycles"]] == [lc["lifecycle_id"]]
    assert out["lifecycles"][0]["accumulated_operating_hours"] == 2.0

    later = t + timedelta(hours=24)
    body = {"until": iso(later), "operating_hours": 0.5, "cycles": 20}
    assert (
        client.post(f"/api/lifecycles/{lc['lifecycle_id']}/usage", body, role="engineer").status_code == 200
    )
    after = client.get(f"/api/components/{cid}/aging", params={"at": iso(later)}).json()
    lcs = client.get(f"/api/components/{cid}/lifecycles").json()
    assert len(lcs) == 1 and lcs[0]["status"] == "ACTIVE" and lcs[0]["installed_at"] == lc["installed_at"]
    assert after["lifecycle_id"] == before["lifecycle_id"]
    assert after["installed_at"] == before["installed_at"]
    assert after["operating_hours"] == pytest.approx(before["operating_hours"] + 0.5)
    assert after["cycles"] == before["cycles"] + 20
    assert after["calendar_hours"] == pytest.approx(before["calendar_hours"] + 24)
    assert after["maintenance_since_install"] == 1 and after["last_maintenance_at"]
