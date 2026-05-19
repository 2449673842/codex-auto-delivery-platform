from fastapi import APIRouter

from app.config import settings

router = APIRouter(tags=["health"])


@router.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "codex-auto-delivery",
        "version": "0.1.0",
        "agent": "ai2",
        "db": settings.db_url,
    }
