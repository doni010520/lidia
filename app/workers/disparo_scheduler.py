"""Worker: disparo_scheduler — verifica disparos agendados a cada 1min."""
from __future__ import annotations

import asyncio

from loguru import logger
from sqlalchemy import func, select

from app.core.config import settings
from app.db import async_session_factory
from app.models.disparos import Disparo
from app.services.disparo_service import is_business_hours


async def check_scheduled_disparos() -> int:
    """Verifica disparos agendados e dispara os que estão na hora."""
    if settings.disparos_business_hours_enabled and not is_business_hours():
        return 0

    async with async_session_factory() as db:
        # Lock: já tem um enviando?
        em_andamento = await db.scalar(
            select(func.count(Disparo.id)).where(Disparo.status == "enviando")
        )
        if (em_andamento or 0) > 0:
            return 0

        # Pega o próximo agendado
        result = await db.execute(
            select(Disparo)
            .where(
                Disparo.status == "agendado",
                Disparo.agendado_para <= func.now(),
            )
            .order_by(Disparo.agendado_para.asc())
            .limit(1)
        )
        disparo = result.scalar_one_or_none()
        if not disparo:
            return 0

        # Move para enviando
        disparo.status = "enviando"
        await db.commit()

    # Dispara em background
    from app.workers.disparo_runner import run_disparo
    asyncio.create_task(run_disparo(disparo.id))
    logger.info(f"Disparo agendado {disparo.id} iniciado pelo scheduler")
    return 1
