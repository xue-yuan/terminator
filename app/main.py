from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.api.v1.api import api_router
from app.core.config import settings
from app.db.session import engine


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.2.0",
    description="Workout tracking API",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=None,
    lifespan=lifespan,
)

cors_origins = list(settings.BACKEND_CORS_ORIGINS)
if settings.ENVIRONMENT == "local":
    cors_origins += ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:4173"]
if cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    return {"status": "ok"}


# Serve the built PWA from the same origin when it exists (`pnpm build`).
_dist: Path = settings.FRONTEND_DIST.resolve()
_NO_CACHE = {"Cache-Control": "no-cache"}

if _dist.is_dir():

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        file = (_dist / path).resolve()
        if path and file.is_file() and file.is_relative_to(_dist):
            hashed = file.parent.name == "assets"
            headers = {"Cache-Control": "public, max-age=31536000, immutable"} if hashed else _NO_CACHE
            return FileResponse(file, headers=headers)
        # A missing API route or build asset is a real 404. Answering with
        # index.html would hand a stale page (e.g. after a deploy) HTML where it
        # expects JavaScript.
        if path.startswith(("api/", "assets/")):
            raise HTTPException(status_code=404)
        return FileResponse(_dist / "index.html", headers=_NO_CACHE)
