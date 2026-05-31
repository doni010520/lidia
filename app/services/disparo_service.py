"""Service layer para disparos — validações, queries, lock global."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.conversation import Contact
from app.models.disparos import Disparo

_SP_TZ = ZoneInfo("America/Sao_Paulo")


async def check_lock(db: AsyncSession) -> bool:
    """Retorna True se já existe um disparo com status 'enviando'."""
    count = await db.scalar(
        select(func.count(Disparo.id)).where(Disparo.status == "enviando")
    )
    return (count or 0) > 0


async def fetch_contatos(db: AsyncSession, disparo: Disparo) -> list[dict]:
    """Busca contatos elegíveis para o disparo."""
    if disparo.filtro_telefones:
        result = await db.execute(
            select(Contact).where(Contact.telefone.in_(disparo.filtro_telefones))
        )
    else:
        stmt = select(Contact).where(
            Contact.ai_enabled == True,
            Contact.is_blocked == False,
            Contact.telefone.isnot(None),
            Contact.telefone != "",
        )
        if disparo.filtro_status:
            stmt = stmt.where(Contact.status == disparo.filtro_status)
        result = await db.execute(stmt)

    return [
        {"telefone": c.telefone, "nome": c.nome or c.full_name or ""}
        for c in result.scalars().all()
    ]


async def count_contatos(db: AsyncSession, status_filter: str | None = None) -> int:
    """Conta contatos elegíveis (para preview no frontend)."""
    stmt = select(func.count(Contact.id)).where(
        Contact.ai_enabled == True,
        Contact.is_blocked == False,
        Contact.telefone.isnot(None),
        Contact.telefone != "",
    )
    if status_filter:
        stmt = stmt.where(Contact.status == status_filter)
    return await db.scalar(stmt) or 0


def is_business_hours() -> bool:
    """Brasília (UTC-3): Seg-Sex 7:30-18:00, Sáb 8:00-13:00, Dom fechado."""
    now = datetime.now(_SP_TZ)
    weekday = now.weekday()
    hour_decimal = now.hour + now.minute / 60

    if weekday <= 4:
        return 7.5 <= hour_decimal < 18.0
    if weekday == 5:
        return 8.0 <= hour_decimal < 13.0
    return False
