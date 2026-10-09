"""T008: the Data Source Studio fixture is reproducible, simulated, and safe to expose."""

import json
import re

from app.datasource.schemas import DataSourceConfig, QueryTemplate, SourceMetadata
from app.signals.schemas import SignalConfigVersion, SignalMapping
from app.simulation.golden import DATA_DIR
from app.simulation.studio_fixture import build_studio

FIXTURE = DATA_DIR / "fixtures" / "studio_demo.json"


def studio() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_fixture_matches_generator():
    assert studio() == json.loads(json.dumps(build_studio(DATA_DIR)))


def test_contract_objects_validate():
    s = studio()
    src = DataSourceConfig.model_validate(s["data_source"])
    assert src.is_simulated and src.read_only
    assert SourceMetadata.model_validate(s["metadata"]).is_simulated
    for t in s["templates"]:
        QueryTemplate.model_validate(t)
    for m in s["suggested_mappings"]:
        SignalMapping.model_validate(m)
    for v in s["versions"]:
        assert "simulated history" in SignalConfigVersion.model_validate(v).comment


def test_no_credentials_and_read_only_sql():
    s = studio()
    assert s["data_source"]["credential_ref"].startswith("secret://")
    assert "password" not in FIXTURE.read_text(encoding="utf-8").lower()
    for sql in s["template_sql"].values():
        assert sql.startswith("SELECT ") and "LIMIT" in sql
        assert not re.search(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|GRANT)\b", sql, re.I)
        params = set(re.findall(r":([a-z_]+)", sql))
        template = next(t for t in s["templates"] if s["template_sql"][t["template_id"]] == sql)
        assert params == {p["name"] for p in template["parameters"]}


def test_previews_cover_each_scenario_fault():
    p = studio()["previews"]
    trq = [t for t, _ in p["SIM-S13"]["series"]["M01_BS1_TRQ"]]
    spd = [t for t, _ in p["SIM-S13"]["series"]["M01_BS1_SPD"]]
    assert len(trq) < len(spd)  # MISSING fault
    ext = [t for t, _ in p["SIM-S13"]["series"]["M01_CY1_EXT"]]
    assert len(ext) > len(set(ext))  # DUPLICATE fault
    lm = [t for t, _ in p["SIM-S14"]["series"]["M01_LM1_SPD"]]
    assert lm != sorted(lm)  # OUT_OF_ORDER fault
    rel = [v for _, v in p["SIM-S16"]["series"]["M01_VC1_REL"]]
    assert max(rel) / min(rel) > 100  # UNIT_SCALE fault starts inside the window
    clean = [t for t, _ in p["SIM-S01"]["series"]["M01_BS1_TRQ"]]
    assert clean == sorted(set(clean))
