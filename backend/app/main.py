from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="Journey-planning API for supported South Indian cities and transport hubs.",
    version=settings.app_version,
    debug=settings.debug,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(api_router)


@app.get("/", tags=["System"])
async def root() -> dict[str, str]:
    """Return basic information about the API."""

    return {
        "message": "South India Travel Guide API",
        "documentation": "/docs",
    }