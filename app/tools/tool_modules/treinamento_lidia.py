"""Tool: treinamento_LidIA — ADMIN: dispara re-vectorização da base."""
from __future__ import annotations

import asyncio

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession


async def execute(
    args: dict,
    phone: str,
    db: AsyncSession,
) -> str:
    """Dispara re-vectorização completa em background."""

    async def _run_training():
        try:
            from app.workers.sheets_sync import run_all_syncs
            results = await run_all_syncs()
            logger.info(f"Treinamento completo: {results}")
        except Exception:
            logger.exception("Erro no treinamento disparado por admin")

    asyncio.create_task(_run_training())

    logger.bind(phone=phone).info("Treinamento disparado por admin")
    return (
        "Re-vectorização da base de conhecimento iniciada em background. "
        "O processo pode levar alguns minutos."
    )
