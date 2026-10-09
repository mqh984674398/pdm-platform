"""Query service fixtures: a SQLite telemetry source seeded from S13 and a throwaway app database."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.core.audit  # noqa: F401  (registers tables)
import app.datasource.query_service.registry  # noqa: F401
from app.core.db import Base, get_session
from app.datasource.query_service.sources import DataSourceRegistry
from app.datasource.sql import SqlAdapter
from app.main import create_app

from ..datasource.conftest import IOTSHARP_LIKE, seed_iotsharp_like, source_config

SECRET_URL_MARKER = "iot-secret.db"


@pytest.fixture(scope="session")
def source_url(tmp_path_factory):
    url = f"sqlite:///{tmp_path_factory.mktemp('src') / SECRET_URL_MARKER}"
    seed_iotsharp_like(url, "S13")
    return url


@pytest.fixture
def make_app(source_url, tmp_path):
    def build(**config):
        cfg = source_config(data_source_id="iot", credential_ref="secret://pdm/iot-readonly", **config)
        adapter = SqlAdapter(cfg, IOTSHARP_LIKE, source_url, acquire_timeout_s=0.05, max_concurrency=1)
        reg = DataSourceRegistry()
        reg.add(cfg, adapter)
        engine = create_engine(f"sqlite:///{tmp_path / 'app.db'}")
        Base.metadata.create_all(engine)
        factory = sessionmaker(engine, expire_on_commit=False)

        def session():
            with factory() as s:
                yield s

        application = create_app(sources=reg)
        application.dependency_overrides[get_session] = session
        return application

    return build


class Client:
    def __init__(self, application):
        self.http = TestClient(application)

    def as_(self, role: str, user: str = "u1"):
        return {"X-PDM-User": user, "X-PDM-Role": role}

    def get(self, path, role="viewer", **kw):
        return self.http.get(path, headers=self.as_(role), **kw)

    def post(self, path, body, role="viewer"):
        return self.http.post(path, json=body, headers=self.as_(role))

    def put(self, path, body, role="admin"):
        return self.http.put(path, json=body, headers=self.as_(role))

    def delete(self, path, role="admin"):
        return self.http.delete(path, headers=self.as_(role))


@pytest.fixture
def client(make_app):
    return Client(make_app())


def by_key_spec(**overrides):
    spec = {
        "template_id": "telemetry-by-key-range",
        "name": {"zh": "按信号键查询时间段", "en": "Signal key over a time range"},
        "description": {"zh": "读取原始值。", "en": "Reads raw values."},
        "data_source_id": "iot",
        "parameters": [
            {"name": "device_id", "type": "IDENTIFIER", "label": {"zh": "设备", "en": "Device"}},
            {"name": "key_name", "type": "IDENTIFIER", "label": {"zh": "信号键", "en": "Key"}},
            {"name": "start", "type": "TIMESTAMP", "label": {"zh": "开始", "en": "Start"}},
            {"name": "end", "type": "TIMESTAMP", "label": {"zh": "结束", "en": "End"}},
        ],
        "sql": (
            "SELECT deviceid, keyname, datetime AS ts, value_double FROM telemetrydata "
            "WHERE deviceid = :device_id AND keyname = :key_name "
            "AND datetime >= :start AND datetime < :end ORDER BY datetime LIMIT 200000"
        ),
        "max_rows": 200000,
        "max_range_hours": 48,
    }
    spec.update(overrides)
    return spec
