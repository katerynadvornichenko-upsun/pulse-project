from fastapi import APIRouter, FastAPI

from pulse import __version__
from pulse.features.issues.router import router as issues_router
from pulse.features.projects.router import router as projects_router
from pulse.lib.errors import register_error_handlers


def create_app() -> FastAPI:
    """All routes live under /api so the same paths work everywhere:

    - Vite dev server proxies /api to this app unchanged.
    - Upsun routes https://{default}/api to this app unchanged.
    """
    app = FastAPI(title="Pulse API", version=__version__)
    register_error_handlers(app)

    api = APIRouter(prefix="/api")

    @api.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    api.include_router(projects_router)
    api.include_router(issues_router)
    app.include_router(api)
    return app


app = create_app()
