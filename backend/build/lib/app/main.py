from pathlib import Path

from fastapi import FastAPI

from app import __version__
from app.api import (
    alarms,
    auth,
    baselines,
    datasources,
    equipment,
    errors,
    fleet,
    health,
    llm,
    optimization,
    pipeline,
    pipeline_config,
    plant,
    quality,
    query,
    registry,
    signals,
    studio,
    timeseries,
)
from app.core.config import get_settings
from app.core.modules import require_module
from app.datasource.query_service.service import QueryService
from app.datasource.query_service.sources import DataSourceRegistry


def create_app(sources: DataSourceRegistry | None = None) -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=__version__)
    if settings.auth_mode == "local" and len(settings.secret_key) < 32:
        raise RuntimeError("PDM_AUTH_MODE=local needs PDM_SECRET_KEY with at least 32 characters")
    if sources is None:
        path = settings.datasources_file
        sources = (
            DataSourceRegistry.from_file(Path(path), allow_production=settings.production_data_approved)
            if path
            else DataSourceRegistry()
        )
    app.state.sources = sources
    app.state.query_service = QueryService(sources)
    errors.install(app)

    @app.middleware("http")
    async def security_headers(request, call_next):  # T028 security review SR-08
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        return resp

    app.include_router(health.router, prefix="/api")
    app.include_router(query.router, prefix="/api", dependencies=[require_module("signals")])
    app.include_router(signals.router, prefix="/api")
    app.include_router(studio.router, prefix="/api", dependencies=[require_module("signals")])
    app.include_router(quality.router, prefix="/api", dependencies=[require_module("signals")])
    app.include_router(datasources.router, prefix="/api")
    app.include_router(pipeline_config.router, prefix="/api")
    app.include_router(equipment.router, prefix="/api")
    app.include_router(plant.router, prefix="/api")
    app.include_router(pipeline.router, prefix="/api", dependencies=[require_module("alarms")])
    app.include_router(baselines.router, prefix="/api")
    app.include_router(alarms.router, prefix="/api")
    app.include_router(timeseries.router, prefix="/api")
    app.include_router(fleet.router, prefix="/api")
    app.include_router(optimization.router, prefix="/api", dependencies=[require_module("optimization")])
    # the optimization screen proposes decision-config candidates to the registry
    app.include_router(
        registry.router, prefix="/api", dependencies=[require_module("models", "optimization")]
    )
    app.include_router(llm.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    if settings.static_dir:
        mount_frontend(app, Path(settings.static_dir))
    return app


def mount_frontend(app: FastAPI, root: Path) -> None:
    """Serve the built browser client on the same port (STK-05); unknown paths get index.html."""
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    index = root / "index.html"
    if not index.is_file():
        raise RuntimeError(f"PDM_STATIC_DIR {root} has no index.html; build the frontend first")
    app.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            from fastapi import HTTPException

            raise HTTPException(404, "not found")
        f = (root / path).resolve()
        if path and f.is_file() and root.resolve() in f.parents:
            return FileResponse(f)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})


app = create_app()
