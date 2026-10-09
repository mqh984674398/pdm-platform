from fastapi import FastAPI

from app import __version__
from app.api import health
from app.core.config import get_settings


def create_app() -> FastAPI:
    app = FastAPI(title=get_settings().app_name, version=__version__)
    app.include_router(health.router, prefix="/api")
    return app


app = create_app()
