"""Tool: plano_de_leitura — plano de leitura bíblica diário.

Replica o subworkflow plano_de_leitura do n8n:
1. SELECT em plano_de_leitura (toda a tabela ou filtro por data)
2. Formata resultado para o LLM processar
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from loguru import logger
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plano_leitura import PlanoLeitura

_SP_TZ = ZoneInfo("America/Sao_Paulo")


async def execute(
    args: dict,
    phone: str,
    db: AsyncSession,
) -> str:
    descricao = args.get("descricao", "").lower().strip()
    today = datetime.now(_SP_TZ).date()

    # Determinar escopo da busca
    if any(w in descricao for w in ["hoje", "today", "agora", "dia"]):
        # Leitura do dia
        result = await db.execute(
            select(PlanoLeitura).where(PlanoLeitura.data == today)
        )
        rows = result.scalars().all()
        scope = f"hoje ({today.strftime('%d/%m/%Y')})"

    elif any(w in descricao for w in ["semana", "semanal", "week"]):
        # Leitura da semana (seg-dom)
        weekday = today.weekday()
        start = today - timedelta(days=weekday)
        end = start + timedelta(days=6)
        result = await db.execute(
            select(PlanoLeitura)
            .where(and_(PlanoLeitura.data >= start, PlanoLeitura.data <= end))
            .order_by(PlanoLeitura.data.asc())
        )
        rows = result.scalars().all()
        scope = f"semana ({start.strftime('%d/%m')} a {end.strftime('%d/%m')})"

    elif any(w in descricao for w in ["amanhã", "amanha", "tomorrow"]):
        tomorrow = today + timedelta(days=1)
        result = await db.execute(
            select(PlanoLeitura).where(PlanoLeitura.data == tomorrow)
        )
        rows = result.scalars().all()
        scope = f"amanhã ({tomorrow.strftime('%d/%m/%Y')})"

    elif any(w in descricao for w in ["cronograma", "todo", "completo", "geral"]):
        # Próximos 30 dias
        result = await db.execute(
            select(PlanoLeitura)
            .where(and_(PlanoLeitura.data >= today, PlanoLeitura.data <= today + timedelta(days=30)))
            .order_by(PlanoLeitura.data.asc())
        )
        rows = result.scalars().all()
        scope = f"próximos 30 dias"

    else:
        # Default: hoje + próximos 3 dias
        result = await db.execute(
            select(PlanoLeitura)
            .where(and_(PlanoLeitura.data >= today, PlanoLeitura.data <= today + timedelta(days=3)))
            .order_by(PlanoLeitura.data.asc())
        )
        rows = result.scalars().all()
        scope = f"hoje e próximos dias"

    if not rows:
        return f"Não há leitura cadastrada para {scope}."

    # Formatar
    lines = [f"📖 Plano de leitura — {scope}:"]
    for row in rows:
        dt_str = row.data.strftime("%d/%m (%a)") if row.data else "?"
        parts = [f"📅 {dt_str}"]
        if row.livro:
            parts.append(f"Livro: {row.livro}")
        if row.leitura:
            parts.append(f"Leitura: {row.leitura}")
        if row.capitulos:
            parts.append(f"Capítulos: {row.capitulos}")
        if row.semana:
            parts.append(f"Semana {row.semana}")
        lines.append(" | ".join(parts))

    return "\n".join(lines)
