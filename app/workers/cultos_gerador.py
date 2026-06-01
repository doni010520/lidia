"""Worker: cultos_gerador - dia 1 do mes 1h BR."""
from __future__ import annotations
from loguru import logger
from sqlalchemy import text
from app.core.config import settings
from app.db import async_session_factory


async def gerar_cultos_proximos_meses() -> int:
    meses = getattr(settings, "cultos_dominicais_meses_a_frente", 3)
    async with async_session_factory() as db:
        try:
            await db.execute(text("SELECT gerar_cultos_dominicais(:m)"), {"m": meses})
            await db.commit()
        except Exception:
            logger.exception("Falha em gerar_cultos_dominicais")
            return 0
        result = await db.execute(text("""
            SELECT COUNT(*) FROM eventos_paes
            WHERE nome = 'Culto aos domingos' AND data_inicio >= CURRENT_DATE
        """))
        total = result.scalar() or 0
    logger.info(f"Cultos dominicais gerados ({meses} meses): {total} futuros")
    return total
