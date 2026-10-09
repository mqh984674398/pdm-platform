"""Feature store: immutable schema versions and deterministic vectors (L4-04)."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.monitoring.features.store  # noqa: F401
from app.core.db import Base
from app.equipment.schemas import ComponentType
from app.monitoring.features.definitions import FEATURE_SETS
from app.monitoring.features.store import FeatureConflictError, FeatureStore

from ..datasource.conftest import PG_URL
from .conftest import extraction


@pytest.fixture
def store(tmp_path):
    engine = create_engine(PG_URL or f"sqlite:///{tmp_path / 'f.db'}")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        st = FeatureStore(s)
        st.register_all()
        yield st
    engine.dispose()


def test_published_version_is_immutable(store):
    fs = FEATURE_SETS[ComponentType.BALL_SCREW]
    store.register(fs)  # same definition: no-op
    changed = fs.model_copy(update={"features": fs.features[:-1]})
    with pytest.raises(FeatureConflictError):
        store.register(changed)
    store.register(changed.model_copy(update={"version": "1.1.0"}))
    assert store.schema("ball_screw@1.1.0").features == fs.features[:-1]


def test_vectors_round_trip_and_save_is_idempotent(store):
    vs = extraction("S12").vectors
    assert store.save(vs) == len(vs)
    assert store.save(vs) == 0
    got = store.vectors("M01-BS1", feature_ref="ball_screw@1.0.0")
    assert got == [v for v in vs if v.component_id == "M01-BS1"]
    lc2 = store.vectors("M01-BS1", lifecycle_id="M01-BS1-LC2")
    assert lc2 and all(v.lifecycle_id == "M01-BS1-LC2" for v in lc2)


def test_different_values_for_a_stored_window_are_refused(store):
    v = extraction("S01").vectors[0]
    store.save([v])
    changed = v.model_copy(update={"values": {k: 0.0 for k in v.values}})
    with pytest.raises(FeatureConflictError):
        store.save([changed])


def test_values_must_match_the_schema(store):
    v = extraction("S01").vectors[0]
    with pytest.raises(FeatureConflictError):
        store.save([v.model_copy(update={"values": {"bogus": 1.0}})])
    with pytest.raises(KeyError):
        store.save([v.model_copy(update={"feature_ref": "ball_screw@9.9.9"})])
