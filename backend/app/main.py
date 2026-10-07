from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.v1 import auth, oauth, users
from app.core.config import settings
from app.core.database import engine
from app.core.exception_handlers import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware
from app.core.observability import configure_opentelemetry, configure_sentry

# Configured before anything else runs, so nothing logs through the
# stdlib's unconfigured default handler.
configure_logging()
configure_sentry()


FRONTEND_DIR = Path(__file__).parent / "frontend"

logger = get_logger("app.main")


def custom_generate_unique_id(route: APIRoute) -> str:
    # Stable, predictable method names in the generated OpenAPI client
    # (frontend/src/client — see the ground-template plan, WS9.2). Without
    # this, `openapi-ts` derives names from FastAPI's auto-generated
    # operation ids, which shift whenever a route's path or function name
    # changes and churn the generated client for no real reason.
    # Not every route has a tag (e.g., the Prometheus /metrics route added
    # below has none) — fall back to the plain route name rather than
    # assuming route.tags[0] exists.
    if route.tags:
        return f"{route.tags[0]}-{route.name}"
    return route.name


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Required by FastAPI's lifespan signature; unused here, nothing
    # at a startup needs the app instance itself yet.
    # Schema changes come from Alembic (`scripts/prestart.sh` runs
    # `alembic upgrade head` before the app starts), never from
    # `Base.metadata.create_all()` here — see the ground-template plan's
    # F2 finding. Tests still use `create_all()` directly in
    # `tests/conftest.py`, which is a separate, deliberate shortcut.
    logger.info("app_startup", environment=settings.ENVIRONMENT)
    # await create_tables()
    yield
    await engine.dispose()
    logger.info("app_shutdown")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    generate_unique_id_function=custom_generate_unique_id,
)

register_exception_handlers(app)
configure_opentelemetry(app)

app.add_middleware(RequestContextMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(oauth.router)
app.include_router(users.router)

# Exposes GET /metrics in Prometheus text format — request counts, latency
# histograms, in-progress requests, by path/method/status. Always on:
# unlike OTEL_ENABLED (which ships spans to a collector over the network),
# this just serves a local text endpoint for something else to scrape, so
# there's no equivalent "nothing to scrape it yet" cost to gate against.
Instrumentator().instrument(app).expose(app, include_in_schema=False)


@app.get("/health", tags=["health"])
async def health_check() -> dict:
    """Liveness only — is the process up. See /health/ready for a DB check."""
    return {"status": "ok", "version": settings.APP_VERSION}


@app.get("/health/ready", tags=["health"])
async def readiness_check() -> dict:
    """Readiness — can we actually reach the database. Used by the
    orchestrator (Compose health check / Coolify) to gate traffic, not just
    "is the process running".
    """
    from sqlalchemy import text

    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return {"status": "ok"}
