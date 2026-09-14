"""Tool: buscar_evento — consulta eventos do Diacon (fonte de verdade).

Fluxo:
1. GET /events/upcoming?from=&to= → Diacon retorna os eventos da janela (até 90 dias).
2. Filtro local por nome (ILIKE-like, normalizado) se nome_evento veio.
3. Filtro local por janela de data se data_inicio/data_fim vieram.
4. Se vazio → "não está na agenda". Sem fallback para a base de conhecimento:
   evento é só da Diacon.

A Diacon ainda não expõe filtros server-side de data/nome,
então fazemos no cliente. Quando ela expor, simplifica.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import diacon_client

_SP_TZ = ZoneInfo("America/Sao_Paulo")
_MAX_LIMIT = 500   # a Diacon devolveu 122 eventos em 90 dias (13/09/26)
_JANELA_DIAS = 90  # teto do `to` na Diacon


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

    # Janela explícita. Antes era limit=20 sem datas: cultos e reuniões enchiam
    # a cota, a agenda acabava em 24/09 e o Cursilho de outubro "não existia" —
    # caía no RAG e saía link velho da planilha.
    today = datetime.now(_SP_TZ).date()
    date_from = data_inicio or today
    date_to = data_fim or (date_from + timedelta(days=_JANELA_DIAS))
    try:
        data = await diacon_client.events_upcoming(
            limit=_MAX_LIMIT, date_from=date_from, date_to=date_to,
        )
    except diacon_client.DiaconError as e:
        logger.warning(f"buscar_evento: Diacon {e.code} {e}")
        return (
            "Não consegui consultar a agenda da Diacon agora. Não tenho como confirmar "
            "data, horário, local ou link — peça para a pessoa tentar de novo em alguns "
            "minutos ou falar com a Secretaria."
        )

    eventos = data.get("events", []) or []
    if not eventos:
        return _fora_da_agenda(nome_evento, date_from, date_to)

    # ── Filtros locais ──
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
            "has_registration": ev.get("has_registration"),
            "_date": ev_date,
            "_hora": ev_hora,
            "_end_date": ev_end_date,
        })

    if not filtered:
        return _fora_da_agenda(nome_evento, date_from, date_to)

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
        # Dois eventos parecidos nos mesmos dias (13/09: "Imersão Céus Abertos" e
        # "Imersão de Oração") — só um tem inscrição; é esse o link de inscrição.
        if ev["has_registration"] is True:
            parts.append("Inscrição: aberta")
        elif ev["has_registration"] is False:
            parts.append("Inscrição: não tem")
        if ev["url"]:
            parts.append(f"Link: {ev['url']}")
        lines.append(" | ".join(parts))

    return f"Encontrados {len(filtered)} evento(s):\n\n" + "\n\n".join(lines)


def _fora_da_agenda(nome_evento: str, date_from: date, date_to: date) -> str:
    """Evento é só da Diacon: sem fallback para a base de conhecimento.

    O fallback RAG devolvia agenda velha — link da Conferência 30 Anos já
    encerrada (11/09) e horário errado da Imersão vindo das fichas do n8n (13/09).
    """
    periodo = f"entre {date_from.strftime('%d/%m/%Y')} e {date_to.strftime('%d/%m/%Y')}"
    if nome_evento:
        return (
            f"'{nome_evento}' não está na agenda da Diacon {periodo}. "
            "Não tenho data, horário, local nem link desse evento."
        )
    return f"Não há eventos na agenda da Diacon {periodo}."
