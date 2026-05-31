from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text as sa_text

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "lidia"}


@router.get("/ready")
async def ready() -> dict:
    """Verifica se dependências estão acessíveis."""
    from app.services.deps import get_buffer_service

    checks: dict[str, str] = {}

    # Redis
    try:
        buffer = get_buffer_service()
        if buffer.redis:
            await buffer.redis.ping()
            checks["redis"] = "ok"
        else:
            checks["redis"] = "not_connected"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"

    # Postgres
    try:
        from app.db import engine
        async with engine.connect() as conn:
            await conn.execute(sa_text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:
        checks["postgres"] = f"error: {exc}"

    all_ok = all(v == "ok" for v in checks.values())
    return {"status": "ready" if all_ok else "degraded", "checks": checks}
