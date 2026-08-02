from fastapi import APIRouter

from app.core.config import get_settings

settings = get_settings()

api_router = APIRouter(prefix=settings.api_v1_prefix)


@api_router.get("/health", tags=["System"])
async def health_check() -> dict[str, str]:
    """Confirm that the API process is running."""

    return {
        "status": "ok",
        "version": settings.app_version,
    }