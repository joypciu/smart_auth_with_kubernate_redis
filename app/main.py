from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from redis.asyncio import from_url as redis_from_url
from starlette.responses import FileResponse, Response
import structlog

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.db.session import close_engine
from app.middleware.observability import ObservabilityMiddleware

configure_logging()
logger = structlog.get_logger(__name__)
web_directory = Path(__file__).parent / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("application_starting", environment=settings.app_env)
    app.state.redis = redis_from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
    yield
    logger.info("application_stopping")
    await app.state.redis.aclose()
    await close_engine()


app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(ObservabilityMiddleware)
app.mount("/assets", StaticFiles(directory=web_directory), name="assets")


@app.get("/", tags=["root"])
async def read_root() -> FileResponse:
    return FileResponse(web_directory / "index.html")


@app.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


app.include_router(api_router, prefix=settings.api_v1_prefix)


