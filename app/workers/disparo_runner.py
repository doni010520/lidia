"""Worker: disparo_runner — executa um disparo (loop de envio).

Toggle de chatbot_stopWhenYouSendMsg: desliga antes do loop,
restaura no finally (mesmo em crash).
"""
from __future__ import annotations

import asyncio
import uuid

from loguru import logger
from sqlalchemy import select

from app.core.config import settings
from app.db import async_session_factory
from app.models.disparos import Disparo, DisparoLog
from app.services.deps import get_uaz_client
from app.services.disparo_service import fetch_contatos, is_business_hours


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
    """Loop principal de envio."""
    async with async_session_factory() as db:
        disparo = await db.get(Disparo, disparo_id)
        if not disparo or disparo.status != "enviando":
            return

        # Verificar horário comercial
        if settings.disparos_business_hours_enabled and not is_business_hours():
            logger.info(f"Disparo {disparo_id} fora de horário comercial → agendado")
            disparo.status = "agendado"
            await db.commit()
            return

        # Buscar contatos
        contatos = await fetch_contatos(db, disparo)
        disparo.total = len(contatos)
        await db.commit()

        if not contatos:
            disparo.status = "concluido"
            await db.commit()
            logger.info(f"Disparo {disparo_id} sem contatos elegíveis → concluído")
            return

        uaz = get_uaz_client()
        enviados = 0
        falhas = 0

        for contato in contatos:
            # Refresh: cancelamento mid-loop
            await db.refresh(disparo)
            if disparo.status == "cancelado":
                logger.info(f"Disparo {disparo_id} cancelado mid-loop")
                return

            # Horário comercial mid-loop
            if settings.disparos_business_hours_enabled and not is_business_hours():
                logger.info(f"Disparo {disparo_id} saiu do horário comercial mid-loop → agendado")
                disparo.status = "agendado"
                await db.commit()
                return

            # Idempotência: pular se já enviado
            existing = await db.scalar(
                select(DisparoLog).where(
                    DisparoLog.disparo_id == disparo_id,
                    DisparoLog.telefone == contato["telefone"],
                )
            )
            if existing:
                continue

            # Envio
            try:
                if disparo.tipo == "contato":
                    # 1) mensagem de texto  2) cartão de contato (vCard)
                    await uaz.send_text(
                        contato["telefone"],
                        disparo.legenda or "",
                        delay=settings.disparos_delay_seconds * 1000,
                    )
                    await asyncio.sleep(settings.disparos_delay_seconds)
                    await uaz.send_contact(
                        contato["telefone"],
                        full_name=disparo.contato_nome or "",
                        phone_number=disparo.contato_telefone or "",
                        organization=disparo.contato_organizacao,
                        delay=settings.disparos_delay_seconds * 1000,
                    )
                else:
                    await uaz.send_media(
                        number=contato["telefone"],
                        file=disparo.arquivo_url,
                        type=disparo.arquivo_tipo,
                        text=disparo.legenda,
                        delay=settings.disparos_delay_seconds * 1000,
                    )
                log_status = "enviado"
                erro = None
                enviados += 1
            except Exception as e:
                log_status = "falhou"
                erro = str(e)[:500]
                falhas += 1
                logger.exception(f"Falha ao enviar para {contato['telefone']}")

            # Log
            db.add(DisparoLog(
                disparo_id=disparo_id,
                telefone=contato["telefone"],
                nome=contato.get("nome", ""),
                status=log_status,
                erro=erro,
            ))

            # Atualizar contadores
            disparo.enviados = enviados
            disparo.falhas = falhas
            await db.commit()

            # Anti-spam
            await asyncio.sleep(settings.disparos_delay_seconds)

        # Finalizar
        disparo.status = "concluido" if falhas < disparo.total else "falhou"
        await db.commit()
        logger.info(f"Disparo {disparo_id} concluído: {enviados} ok, {falhas} falhas")
