"""Declared, versioned feature sets per component type (L4-04)."""

import re

from app.equipment.schemas import TEMPLATE_ONLY_TYPES, ComponentType
from app.monitoring.features.definitions import FEATURE_SETS

from .conftest import extraction


def test_every_telemetry_type_has_a_versioned_feature_set():
    assert set(FEATURE_SETS) == set(ComponentType) - TEMPLATE_ONLY_TYPES
    refs = set()
    for ctype, fs in FEATURE_SETS.items():
        assert fs.component_type == ctype.value
        assert re.fullmatch(r"\d+\.\d+\.\d+", fs.version)
        assert fs.ref == f"{fs.feature_set}@{fs.version}"
        names = [f.name for f in fs.features]
        assert len(names) == len(set(names))
        assert any(f.residual for f in fs.features), "each set carries a condition-normalized residual"
        assert all(f.description.zh and f.description.en for f in fs.features)
        refs.add(fs.ref)
    assert len(refs) == len(FEATURE_SETS)


def test_vectors_follow_their_declared_schema():
    by_ref = {fs.ref: fs for fs in FEATURE_SETS.values()}
    for sid in ("S01", "S05", "S06", "S07"):
        r = extraction(sid)
        assert r.vectors and r.is_simulated
        for v in r.vectors:
            assert list(v.values) == [f.name for f in by_ref[v.feature_ref].features]
            assert v.is_simulated


def test_template_only_types_get_no_features():
    from app.monitoring.features.extract import extract_features

    from ..equipment.conftest import scenario, series

    sc = scenario("S01")
    comps = {"M01-CAM1": ComponentType.CAM}
    r = extract_features(series("S01"), sc.window(96, 120), comps, {})
    assert r.vectors == [] and r.not_supported == ["M01-CAM1"]
