from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import Settings
from src.core.middleware.request_logging import RequestLoggingMiddleware


def setup_middleware(app: FastAPI, settings: Settings) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLoggingMiddleware)
