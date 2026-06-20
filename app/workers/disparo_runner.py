"""Worker: disparo_runner — executa um disparo (loop de envio).

Toggle de chatbot_stopWhenYouSendMsg: desliga antes do loop,
restaura no finally (mesmo em crash).
"""
from __future__ import annotations

import asyncio
import random
import uuid

from loguru import logger
from sqlalchemy import func, select

from app.core.config import settings
from app.db import async_session_factory
from app.models.disparos import Disparo, DisparoLog
from app.services.deps import get_uaz_client
from app.services.disparo_service import (
    dentro_da_janela,
    fetch_contatos,
    proxima_abertura,
)


async def run_disparo(disparo_id: uuid.UUID) -> None:
    """Entry point — toggle chatbot settings e chama o loop."""
    uaz = get_uaz_client()

    # Desativar pausa nativa antes do loop
    try:
        await uaz.update_chatbot_settings(
            chatbot_enabled=True,
            chatbot_ignore_groups=True,
            chatbot_stop_when_you_send_msg=0,
        )
        logger.info("chatbot_stop desativado para disparo")
    except Exception:
        logger.warning("Falha ao desativar chatbot_stop — seguindo mesmo assim")

    try:
        await _loop_envio(disparo_id)
    finally:
        # Restaurar pausa nativa (sempre)
        try:
            await uaz.update_chatbot_settings(
                chatbot_enabled=True,
                chatbot_ignore_groups=True,
                chatbot_stop_when_you_send_msg=settings.handoff_pause_minutes,
            )
            logger.info("chatbot_stop restaurado após disparo")
        except Exception:
            logger.error(
                "CRÍTICO: falha ao restaurar chatbot_stop. "
                "Verifique uazapi manualmente — pausa automática pode estar desligada."
            )


async def _loop_envio(disparo_id: uuid.UUID) -> None:
    """Loop principal de envio.

    Sessão de banco CURTA por iteração (a espera entre pessoas é longa,
    3–5 min, então não dá pra segurar uma conexão aberta o loop todo).
    Contadores cumulativos a partir de disparo_log (retoma certo após
    pausa de horário comercial).
    """
    # ── Setup: contatos + snapshot dos campos do disparo ──
    async with async_session_factory() as db:
        disparo = await db.get(Disparo, disparo_id)
        if not disparo or disparo.status != "enviando":
            return

        # Fora da janela de envio → agenda pra próxima abertura
        if not dentro_da_janela():
            abertura = proxima_abertura()
            disparo.status = "agendado"
            disparo.agendado_para = abertura
            await db.commit()
            logger.info(f"Disparo {disparo_id} fora da janela → retoma em {abertura.isoformat()}")
            return

        contatos = await fetch_contatos(db, disparo)
        disparo.total = len(contatos)
        await db.commit()

        snap = {
            "tipo": disparo.tipo,
            "legenda": disparo.legenda,
            "arquivo_url": disparo.arquivo_url,
            "arquivo_tipo": disparo.arquivo_tipo,
            "contato_nome": disparo.contato_nome,
            "contato_telefone": disparo.contato_telefone,
            "contato_organizacao": disparo.contato_organizacao,
        }

    if not contatos:
        async with async_session_factory() as db:
            d = await db.get(Disparo, disparo_id)
            if d:
                d.status = "concluido"
                await db.commit()
        logger.info(f"Disparo {disparo_id} sem contatos elegíveis → concluído")
        return

    uaz = get_uaz_client()

    # Contadores cumulativos (sobrevivem a pausas/retomadas)
    async with async_session_factory() as db:
        enviados = await db.scalar(
            select(func.count(DisparoLog.id)).where(
                DisparoLog.disparo_id == disparo_id, DisparoLog.status == "enviado"
            )
        ) or 0
        falhas = await db.scalar(
            select(func.count(DisparoLog.id)).where(
                DisparoLog.disparo_id == disparo_id, DisparoLog.status == "falhou"
            )
        ) or 0

    total = len(contatos)
    for idx, contato in enumerate(contatos):
        telefone = contato["telefone"]

        # ── Checagens de estado (sessão curta) ──
        async with async_session_factory() as db:
            d = await db.get(Disparo, disparo_id)
            if not d or d.status == "cancelado":
                logger.info(f"Disparo {disparo_id} cancelado mid-loop")
                return
            # Fora da janela (ex.: chegou 21h) → pausa e agenda retomada
            if not dentro_da_janela():
                abertura = proxima_abertura()
                d.status = "agendado"
                d.agendado_para = abertura
                await db.commit()
                logger.info(f"Disparo {disparo_id} pausou (janela) → retoma em {abertura.isoformat()}")
                return
            # Idempotência: pular se já enviado
            existing = await db.scalar(
                select(DisparoLog).where(
                    DisparoLog.disparo_id == disparo_id,
                    DisparoLog.telefone == telefone,
                )
            )
            if existing:
                continue

        # ── Envio (fora de qualquer sessão de banco) ──
        try:
            if snap["tipo"] == "contato":
                # 1) mensagem de texto  2) cartão de contato (vCard)
                await uaz.send_text(
                    telefone, snap["legenda"] or "",
                    delay=settings.disparos_delay_seconds * 1000,
                )
                await asyncio.sleep(settings.disparos_delay_seconds)
                await uaz.send_contact(
                    telefone,
                    full_name=snap["contato_nome"] or "",
                    phone_number=snap["contato_telefone"] or "",
                    organization=snap["contato_organizacao"],
                    delay=settings.disparos_delay_seconds * 1000,
                )
            else:
                await uaz.send_media(
                    number=telefone,
                    file=snap["arquivo_url"],
                    type=snap["arquivo_tipo"],
                    text=snap["legenda"],
                    delay=settings.disparos_delay_seconds * 1000,
                )
            log_status = "enviado"
            erro = None
            enviados += 1
        except Exception as e:
            log_status = "falhou"
            erro = str(e)[:500]
            falhas += 1
            logger.exception(f"Falha ao enviar para {telefone}")

        # ── Log + contadores (sessão curta) ──
        async with async_session_factory() as db:
            db.add(DisparoLog(
                disparo_id=disparo_id,
                telefone=telefone,
                nome=contato.get("nome", ""),
                status=log_status,
                erro=erro,
            ))
            d = await db.get(Disparo, disparo_id)
            if d:
                d.enviados = enviados
                d.falhas = falhas
            await db.commit()

        # ── Intervalo aleatório entre pessoas (anti-ban), exceto após o último ──
        if idx < total - 1:
            intervalo = random.randint(
                settings.disparos_intervalo_min_seconds,
                settings.disparos_intervalo_max_seconds,
            )
            logger.info(f"Disparo {disparo_id}: aguardando {intervalo}s até o próximo")
            await asyncio.sleep(intervalo)

    # ── Finalizar ──
    async with async_session_factory() as db:
        d = await db.get(Disparo, disparo_id)
        if d:
            d.status = "concluido" if falhas < (d.total or 0) else "falhou"
            await db.commit()
    logger.info(f"Disparo {disparo_id} concluído: {enviados} ok, {falhas} falhas")
