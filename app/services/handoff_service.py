"""Handoff service — toggle persistente de AI via keywords em mensagens outgoing.

Dois mecanismos combinados (seção 12 do plano):
1. Pausa automática (30min) via chatbot_stopWhenYouSendMsg da uazapi (configurado no lifespan)
2. Toggle persistente: "Roberta aqui!" → ai_enabled=False, "té mais!" → ai_enabled=True
"""
from __future__ import annotations

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.conversation import Contact
from app.schemas.webhook import IncomingMessage


async def handle_outgoing(msg: IncomingMessage, db: AsyncSession) -> None:
    """Processa mensagem from_me para detectar keywords de handoff.

    Chamado pelo webhook handler quando from_me == True.
    """
    text = (msg.text or "").lower().strip()
    if not text:
        return

    # Buscar contato
    result = await db.execute(
        select(Contact).where(Contact.telefone == msg.phone)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        return

    keyword_off = settings.handoff_keyword_off.lower()
    keyword_on = settings.handoff_keyword_on.lower()

    if keyword_off and keyword_off in text:
        if contact.ai_enabled:
            contact.ai_enabled = False
            await db.commit()
            logger.bind(phone=msg.phone).info(
                f"AI DESABILITADA (handoff persistente: '{settings.handoff_keyword_off}')"
            )

    elif keyword_on and keyword_on in text:
        if not contact.ai_enabled:
            contact.ai_enabled = True
            await db.commit()
            logger.bind(phone=msg.phone).info(
                f"AI REABILITADA (handoff encerrado: '{settings.handoff_keyword_on}')"
            )


# ── Pausa automática quando a equipe responde pelo celular ──
# Na uazapi era o chatbot_stopWhenYouSendMsg (nativo). Na Zernio (coexistência)
# a resposta do celular chega como `message.sent` e a pausa é nossa.

def _redis():
    from app.services import media_temp
    return media_temp._r()


async def pausar_ia(phone: str, minutos: int | None = None) -> None:
    m = settings.pausa_humano_minutos if minutos is None else minutos
    await _redis().set(f"pausa_humano:{phone}", "1", ex=m * 60)
    logger.bind(phone=phone).info(f"IA pausada {m} min (equipe respondeu pelo celular)")


async def ia_pausada(phone: str) -> bool:
    try:
        return bool(await _redis().exists(f"pausa_humano:{phone}"))
    except Exception:
        logger.exception("Falha ao checar pausa da IA (seguindo sem pausa)")
        return False
