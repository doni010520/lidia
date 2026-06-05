"""Tool: buscar_evento — consulta eventos do Diacon (fonte de verdade).

Fluxo (Fase 1B):
1. GET /events/upcoming → Diacon retorna próximos eventos publicados.
2. Filtro local por nome (ILIKE-like, normalizado) se nome_evento veio.
3. Filtro local por janela de data se data_inicio/data_fim vieram.
4. Se vazio → fallback RAG.

A Diacon ainda não expõe filtros server-side de data/nome,
então fazemos no cliente. Quando ela expor, simplifica.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import diacon_client
from app.services.rag_service import RAGService

_SP_TZ = ZoneInfo("America/Sao_Paulo")
_MAX_LIMIT = 20


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def _normalize(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s).encode("ASCII", "ignore").decode().lower()
    return s.strip()


def _parse_starts_at(s: str) -> tuple[date | None, str]:
    """Diacon retorna ISO com offset (2026-06-07T19:00:00-03:00)."""
    if not s:
        return None, ""
    try:
        dt = datetime.fromisoformat(s)
        dt_local = dt.astimezone(_SP_TZ) if dt.tzinfo else dt
        return dt_local.date(), dt_local.strftime("%H:%M")
    except Exception:
        return None, ""


async def execute(
    args: dict,
    phone: str,
    db: AsyncSession,
) -> str:
    nome_evento = (args.get("nome_evento") or "").strip()
    data_inicio = _parse_date(args.get("data_inicio"))
    data_fim = _parse_date(args.get("data_fim"))

    if not diacon_client.is_enabled():
        return "Erro: integração Diacon não configurada."

    # Buscar todos os próximos eventos (cap em 20)
    try:
        data = await diacon_client.events_upcoming(limit=_MAX_LIMIT)
    except diacon_client.DiaconError as e:
        logger.warning(f"buscar_evento: Diacon {e.code} {e}")
        # Fallback RAG
        return await _rag_fallback(nome_evento, db)

    eventos = data.get("events", []) or []
    if not eventos:
        return await _rag_fallback(nome_evento, db)

    # ── Filtros locais ──
    today = datetime.now(_SP_TZ).date()
    if not data_inicio and not nome_evento:
        # Default: próximos 60 dias
        data_inicio = today
        data_fim = today + timedelta(days=60)

    norm_query = _normalize(nome_evento) if nome_evento else ""

    filtered = []
    for ev in eventos:
        ev_date, ev_hora = _parse_starts_at(ev.get("starts_at", ""))
        ev_end_date, _ = _parse_starts_at(ev.get("ends_at", ""))

        # Filtro nome
        if norm_query:
            title = _normalize(ev.get("title") or "")
            type_ = _normalize(ev.get("type") or "")
            if norm_query not in title and norm_query not in type_:
                continue

        # Filtro data (intersecção do intervalo do evento com [data_inicio, data_fim])
        if data_inicio:
            limit_end = data_fim or (data_inicio + timedelta(days=120))
            ev_end = ev_end_date or ev_date or limit_end
            ev_start = ev_date or ev_end
            if ev_start > limit_end:
                continue
            if ev_end < data_inicio:
                continue

        filtered.append({
            "title": ev.get("title"),
            "type": ev.get("type"),
            "starts_at": ev.get("starts_at"),
            "ends_at": ev.get("ends_at"),
            "venue": ev.get("venue"),
            "description": ev.get("description_short"),
            "url": ev.get("registration_url"),
            "_date": ev_date,
            "_hora": ev_hora,
            "_end_date": ev_end_date,
        })

    if not filtered:
        return await _rag_fallback(nome_evento, db)

    # ── Formatação ──
    lines = []
    for ev in filtered:
        parts = [f"📌 {ev['title']}"]
        if ev["_date"]:
            dt_str = ev["_date"].strftime("%d/%m/%Y")
            if ev["_end_date"] and ev["_end_date"] != ev["_date"]:
                dt_str += f" a {ev['_end_date'].strftime('%d/%m/%Y')}"
            parts.append(f"Data: {dt_str}")
        if ev["_hora"]:
            parts.append(f"Horário: {ev['_hora']}")
        if ev["venue"]:
            parts.append(f"Local: {ev['venue']}")
        if ev["type"]:
            parts.append(f"Tipo: {ev['type']}")
        if ev["description"]:
            parts.append(f"Descrição: {ev['description']}")
        if ev["url"]:
            parts.append(f"Link: {ev['url']}")
        lines.append(" | ".join(parts))

    return f"Encontrados {len(filtered)} evento(s):\n\n" + "\n\n".join(lines)


async def _rag_fallback(nome_evento: str, db: AsyncSession) -> str:
    """Quando Diacon não retorna nada útil, tenta RAG."""
    query = f"evento {nome_evento}" if nome_evento else "eventos programação PAES"
    logger.debug(f"buscar_evento: Diacon vazio, fallback RAG '{query}'")
    rag = RAGService()
    chunks = await rag.search(query, db, top_k=5)
    if chunks:
        return (
            "Não encontrei eventos no calendário, mas achei na base de conhecimento:\n\n"
            + rag.format_chunks(chunks)
        )
    return "Nenhum evento encontrado para os critérios informados."
