from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from nexusflow import __version__
from nexusflow.api.router import api_router
from nexusflow.cache import redis
from nexusflow.config import settings
from nexusflow.db import engine
from nexusflow.middleware import request_context_middleware


@asynccontextmanager
async def lifespan(
    app: FastAPI,
):
    yield

    # ----------------------------------------------------------
    # Graceful shutdown
    # ----------------------------------------------------------

    await redis.aclose()

    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description=("Production-oriented distributed workflow backend"),
    lifespan=lifespan,
)


# ============================================================
# Middleware
# ============================================================

app.middleware("http")(request_context_middleware)


app.add_middleware(
    GZipMiddleware,
    minimum_size=1000,
    compresslevel=5,
)


if settings.cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "X-Request-ID",
            "X-Process-Time",
        ],
    )


# ============================================================
# API
# ============================================================

app.include_router(
    api_router,
    prefix="/api/v1",
)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "version": __version__,
        "status": "running",
    }
