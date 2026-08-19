"""FastAPI application entrypoint.

Run with:  python -m uvicorn src.main:app --reload --port 8000   (from apps/api/)
See apps/api/README.md "Local Development" for the full setup.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api_router import api_router
from src.core.config import get_settings
from src.core.database import dispose_engine
from src.core.exceptions.handlers import register_exception_handlers
from src.core.logging import configure_logging
from src.core.middleware import setup_middleware

settings = get_settings()
settings.validate_production_safety()
configure_logging(settings.log_level)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    # No connection is opened on startup: the engine is created lazily on first
    # use, so the app still boots (and /health still answers) with no database
    # running. Phase 4 has no routes that touch the database yet.
    yield
    await dispose_engine()


app = FastAPI(
    title="LostIntoSpacE API",
    version="0.1.0",
    debug=False,  # keep error responses consistent (JSON envelope) in every environment
    lifespan=lifespan,
)

setup_middleware(app, settings)
register_exception_handlers(app)
app.include_router(api_router)
