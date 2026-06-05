"""Tool: notificar_time_interno — encaminha demanda pra equipe interna.

Fase 3: Diacon é fonte de verdade. Vai como POST /pastoral.
Mapeamos nossas 19 equipes PAES → 9 áreas da Diacon.

Fallback: se Diacon falhar, ainda grava no Sheets da equipe (write local)
pra equipe Céus Abertos continuar vendo histórico via planilha. Quando
todos estiverem usando o painel Diacon, removemos o fallback.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.equipes import EquipeResponsavel
from app.services import diacon_client, sheets_client

_SP_TZ = ZoneInfo("America/Sao_Paulo")


# Mapa nosso → área Diacon
# (ministry_interest, cell_interest, decision, pastoral_care,
#  visit, follow_up, baptism, discipleship, other)
_EQUIPE_TO_AREA: dict[str, str] = {
    "células": "cell_interest",
    "louvor": "ministry_interest",
    "fluir": "ministry_interest",
    "casais": "ministry_interest",
    "cursilho masculino": "ministry_interest",
    "cursilho feminino": "ministry_interest",
    "oração": "pastoral_care",  # NOTA: pedido pessoal de oração usa pedido_oracao
    "batismo": "baptism",
    "gabinete pastoral": "pastoral_care",
    "casa da esperança": "pastoral_care",
    "dízimos e ofertas": "other",
    "agenda de eventos": "other",
    "decisão": "decision",
    "visita guiada": "visit",
    "dúvidas gerais": "other",
    "apresentação de crianças": "other",
    "ministérios": "ministry_interest",
    "plano de leitura": "other",
    "comunicação": "other",
}


_PRIORIDADE_TO_DIACON: dict[str, str] = {
    "baixa": "low",
    "low": "low",
    "media": "normal",
    "média": "normal",
    "normal": "normal",
    "alta": "high",
    "high": "high",
    "critica": "critical",
    "crítica": "critical",
    "critical": "critical",
}


def _map_area(equipe_nome: str) -> str:
    norm = (equipe_nome or "").strip().lower()
    return _EQUIPE_TO_AREA.get(norm, "other")


async def execute(args: dict, phone: str, db: AsyncSession) -> str:
    tipo = args.get("tipo_situacao", "")
    prioridade_raw = (args.get("prioridade") or "media").lower()
    equipe_nome = args.get("equipe_responsavel", "")
    nome = args.get("nome", "")
    telefone = args.get("telefone") or phone
    detalhes = args.get("detalhes", "")

    if not tipo or not equipe_nome or not detalhes:
        return "Erro: tipo_situacao, equipe_responsavel e detalhes são obrigatórios."

    # ── 1. Buscar equipe na nossa tabela (rotulação) ──
    result = await db.execute(
        select(EquipeResponsavel).where(EquipeResponsavel.equipe.ilike(f"%{equipe_nome}%"))
    )
    equipe = result.scalar_one_or_none()

    if not equipe:
        result = await db.execute(
            select(EquipeResponsavel).where(EquipeResponsavel.equipe.ilike("%Dúvidas Gerais%"))
        )
        equipe = result.scalar_one_or_none()
        if equipe:
            logger.info(f"Equipe '{equipe_nome}' não encontrada → Dúvidas Gerais")

    equipe_label = equipe.equipe if equipe else equipe_nome

    # ── 2. Registrar no Diacon ──
    area = _map_area(equipe_label)
    priority = _PRIORIDADE_TO_DIACON.get(prioridade_raw, "normal")

    sent_diacon = False
    diacon_err = None
    if diacon_client.is_enabled():
        try:
            await diacon_client.pastoral_create(
                area=area,
                title=f"{tipo} — encaminhar à equipe {equipe_label}",
                context=f"Equipe: {equipe_label}\nDetalhes: {detalhes}",
                priority=priority,
                phone=telefone,
                name=nome,
            )
            sent_diacon = True
        except diacon_client.DiaconError as e:
            diacon_err = e
            logger.warning(f"notificar_time_interno: Diacon {e.code} {e}")

    # ── 3. Fallback Sheets (planilha da equipe ou log geral) ──
    sheets_target = (
        (equipe.sheets_log_url if equipe else None)
        or settings.sheets_log_notificacoes_id
    )
    sent_sheets = False
    if sheets_target:
        now = datetime.now(_SP_TZ).strftime("%d/%m/%Y %H:%M")
        try:
            sheets_client.append_row(
                sheets_target,
                "A1",
                [nome, tipo, telefone, detalhes, prioridade_raw, now, equipe_label],
            )
            sent_sheets = True
        except Exception:
            logger.exception(f"Erro ao registrar no Sheets ({sheets_target})")

    if not sent_diacon and not sent_sheets:
        return "Não consegui registrar agora. Tenta de novo em alguns segundos."

    logger.bind(phone=telefone).info(
        f"Notificação: equipe={equipe_label} area={area} "
        f"diacon={'ok' if sent_diacon else (diacon_err.code if diacon_err else 'skip')} "
        f"sheets={'ok' if sent_sheets else 'skip'}"
    )

    return (
        f"Equipe '{equipe_label}' notificada.\n"
        f"Diacon: {'ok' if sent_diacon else 'falhou'} | Sheets: {'ok' if sent_sheets else 'skip'}"
    )
