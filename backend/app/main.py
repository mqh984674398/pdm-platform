from pathlib import Path

from fastapi import FastAPI

from app import __version__
from app.api import errors, health, query
from app.core.config import get_settings
from app.datasource.query_service.service import QueryService
from app.datasource.query_service.sources import DataSourceRegistry


def create_app(sources: DataSourceRegistry | None = None) -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=__version__)
    if sources is None:
        path = settings.datasources_file
        sources = DataSourceRegistry.from_file(Path(path)) if path else DataSourceRegistry()
    app.state.sources = sources
    app.state.query_service = QueryService(sources)
    errors.install(app)
    app.include_router(health.router, prefix="/api")
    app.include_router(query.router, prefix="/api")
    return app


app = create_app()
