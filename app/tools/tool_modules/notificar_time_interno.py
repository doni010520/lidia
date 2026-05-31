"""Tool: notificar_time_interno — notifica equipe interna da PAES."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.equipes import EquipeResponsavel
from app.services import gmail_client, sheets_client
from app.services.deps import get_uaz_client

_SP_TZ = ZoneInfo("America/Sao_Paulo")


async def execute(
    args: dict,
    phone: str,
    db: AsyncSession,
) -> str:
    tipo = args.get("tipo_situacao", "")
    prioridade = args.get("prioridade", "media")
    equipe_nome = args.get("equipe_responsavel", "")
    nome = args.get("nome", "")
    telefone = args.get("telefone", phone)
    detalhes = args.get("detalhes", "")

    if not tipo or not equipe_nome or not detalhes:
        return "Erro: tipo_situacao, equipe_responsavel e detalhes são obrigatórios."

    # 1. Buscar equipe (ILIKE)
    result = await db.execute(
        select(EquipeResponsavel).where(EquipeResponsavel.equipe.ilike(f"%{equipe_nome}%"))
    )
    equipe = result.scalar_one_or_none()

    # Fallback: Dúvidas Gerais
    if not equipe:
        result = await db.execute(
            select(EquipeResponsavel).where(EquipeResponsavel.equipe.ilike("%Dúvidas Gerais%"))
        )
        equipe = result.scalar_one_or_none()
        if equipe:
            logger.info(f"Equipe '{equipe_nome}' não encontrada, fallback para Dúvidas Gerais")

    if not equipe:
        return f"Equipe '{equipe_nome}' não encontrada e fallback 'Dúvidas Gerais' indisponível."

    # 2. Montar mensagem
    now = datetime.now(_SP_TZ).strftime("%d/%m/%Y %H:%M")
    msg = (
        f"📋 *Notificação — {equipe.equipe}*\n\n"
        f"Tipo: {tipo}\n"
        f"Prioridade: {prioridade}\n"
        f"Nome: {nome}\n"
        f"Telefone: {telefone}\n"
        f"Detalhes: {detalhes}\n"
        f"Data: {now}"
    )

    uaz = get_uaz_client()
    sent_wpp = 0
    sent_email = 0

    # 3. WhatsApp para cada responsável
    if equipe.telefones_responsaveis:
        for resp_phone in equipe.telefones_responsaveis:
            try:
                await uaz.send_text(resp_phone, msg)
                sent_wpp += 1
            except Exception:
                logger.exception(f"Erro ao notificar {resp_phone} via WhatsApp")

    # 4. Email para cada email da equipe
    if equipe.emails:
        subject = f"[PAES LidIA] {tipo} — {prioridade} — {nome}"
        for email in equipe.emails:
            try:
                gmail_client.send_email(email, subject, msg.replace("*", ""))
                sent_email += 1
            except Exception:
                logger.exception(f"Erro ao notificar {email} via email")

    # 5. Append em Sheets log
    if settings.sheets_log_notificacoes_id:
        try:
            sheets_client.append_row(
                settings.sheets_log_notificacoes_id,
                "A1",
                [nome, tipo, telefone, detalhes, prioridade, now, equipe.equipe],
            )
        except Exception:
            logger.exception("Erro ao registrar notificação no Sheets")

    logger.bind(phone=telefone).info(
        f"Notificação enviada: {equipe.equipe} (wpp={sent_wpp}, email={sent_email})"
    )
    return (
        f"Equipe '{equipe.equipe}' notificada com sucesso.\n"
        f"WhatsApp: {sent_wpp} mensagens enviadas.\n"
        f"Email: {sent_email} emails enviados."
    )
