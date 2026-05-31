"""Tool: buscar_evento — consulta eventos no DB com fallback RAG.

Replica a lógica do subworkflow buscar_eventos do n8n:
1. SELECT em eventos_paes por data e/ou nome (ILIKE)
2. Se vazio → fallback RAG com "evento {nome_evento}"
3. Retorna formatado para o LLM
"""
from __future__ import annotations

from datetime import date, timedelta
from zoneinfo import ZoneInfo

from loguru import logger
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.eventos import EventoPaes
from app.services.rag_service import RAGService

_SP_TZ = ZoneInfo("America/Sao_Paulo")


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


async def execute(
    args: dict,
    phone: str,
    db: AsyncSession,
) -> str:
    nome_evento = args.get("nome_evento", "").strip()
    data_inicio = _parse_date(args.get("data_inicio"))
    data_fim = _parse_date(args.get("data_fim"))

    # Se nenhum filtro → buscar próximos 30 dias
    if not nome_evento and not data_inicio:
        from datetime import datetime
        today = datetime.now(_SP_TZ).date()
        data_inicio = today
        data_fim = today + timedelta(days=30)

    # ── 1. SQL query ──
    conditions = []
    if nome_evento:
        conditions.append(EventoPaes.nome.ilike(f"%{nome_evento}%"))
    if data_inicio and data_fim:
        # Evento ativo no intervalo: data_inicio do evento <= data_fim busca
        # AND data_inicio busca <= data_final do evento
        conditions.append(
            and_(
                EventoPaes.data_inicio <= data_fim,
                or_(
                    EventoPaes.data_final >= data_inicio,
                    # Se data_final é NULL, usar data_inicio como fim
                    and_(
                        EventoPaes.data_final.is_(None),
                        EventoPaes.data_inicio >= data_inicio,
                    ),
                ),
            )
        )
    elif data_inicio:
        conditions.append(EventoPaes.data_inicio >= data_inicio)

    stmt = select(EventoPaes).order_by(EventoPaes.data_inicio.asc())
    if conditions:
        stmt = stmt.where(and_(*conditions))
    stmt = stmt.limit(20)

    result = await db.execute(stmt)
    eventos = result.scalars().all()

    # ── 2. Se achou → formatar ──
    if eventos:
        lines = []
        for ev in eventos:
            parts = [f"📌 {ev.nome}"]
            if ev.data_inicio:
                dt = ev.data_inicio.strftime("%d/%m/%Y")
                if ev.data_final and ev.data_final != ev.data_inicio:
                    dt += f" a {ev.data_final.strftime('%d/%m/%Y')}"
                parts.append(f"Data: {dt}")
            if ev.hora:
                parts.append(f"Horário: {ev.hora.strftime('%H:%M')}")
            if ev.local:
                parts.append(f"Local: {ev.local}")
            if ev.descricao:
                parts.append(f"Descrição: {ev.descricao}")
            if ev.valor:
                parts.append(f"Valor: {ev.valor}")
            if ev.link:
                parts.append(f"Link: {ev.link}")
            lines.append(" | ".join(parts))

        return f"Encontrados {len(eventos)} evento(s):\n\n" + "\n\n".join(lines)

    # ── 3. Fallback RAG ──
    query = f"evento {nome_evento}" if nome_evento else "eventos programação PAES"
    logger.debug(f"buscar_evento: SQL vazio, fallback RAG '{query}'")

    rag = RAGService()
    chunks = await rag.search(query, db, top_k=5)
    if chunks:
        return "Não encontrei eventos no calendário, mas achei na base de conhecimento:\n\n" + rag.format_chunks(chunks)

    return "Nenhum evento encontrado para os critérios informados."
