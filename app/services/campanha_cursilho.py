"""Campanha 54º Cursilho Masculino (out/2026) — convite em 2 etapas.

1. `enviar_convite`: mensagem curta com botão "Quero saber" (o clique já conta
   como interação pro WhatsApp, o que protege o número da LidIA no disparo).
2. `responder_clique`: quem clica recebe o vídeo do Bispo com o convite e o link.

As duas etapas vão pro histórico (`messages`), então se a pessoa responder
digitando em vez de clicar, a LidIA sabe do que se trata.
"""
from __future__ import annotations

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.conversation_service import save_message
from app.services.uaz_client import UAZClient

BOTAO_ID = "cursilho_quero"
BOTAO_LABEL = "Quero saber 🙏"

VIDEO_URL = "https://lidia.benitechlab.com/static/campanhas/cursilho-masculino.mp4"

CONVITE = (
    "Oi, {nome}! 😊\n\n"
    "O Bispo Miguel Uchoa tem uma novidade pra você.\n\n"
    "Quer saber qual é?"
)

LEGENDA = (
    "Passando para te convocar a levar +1 para Cristo para o Cursilho Masculino, "
    "através da célula que você faz parte.\n\n"
    "Assista agora o vídeo que o Bispo Miguel Uchoa fez com muito carinho e "
    "veja o convite que ele faz.\n\n"
    "O 54º Cursilho Masculino será de 29 de outubro a 01 de novembro. "
    "Vamos levar +1 para Cristo.\n\n"
    "Segue o link para inscrição abaixo:\n\n"
    "https://sysigreja.com/Somos%20PAES/cursilho-masculino"
)


def _primeiro_nome(nome: str | None) -> str:
    return (nome or "").strip().split(" ")[0] if nome and nome.strip() else ""


async def enviar_convite(uaz: UAZClient, db: AsyncSession, phone: str, nome: str | None) -> dict:
    primeiro = _primeiro_nome(nome)
    texto = CONVITE.format(nome=primeiro) if primeiro else CONVITE.replace("Oi, {nome}! ", "Oi! ")
    resp = await uaz._post("/send/menu", {
        "number": phone,
        "type": "button",
        "text": texto,
        "choices": [f"{BOTAO_LABEL}|{BOTAO_ID}"],
        "readchat": True,
    })
    await save_message(db, phone, "assistant", texto)
    await db.commit()
    logger.bind(phone=phone).info("Cursilho: convite com botão enviado")
    return resp


def eh_clique(button_id: str | None) -> bool:
    return button_id == BOTAO_ID


async def responder_clique(uaz: UAZClient, db: AsyncSession, phone: str) -> None:
    await save_message(db, phone, "user", BOTAO_LABEL)
    await uaz.send_media(phone, VIDEO_URL, "video", text=LEGENDA)
    await save_message(db, phone, "assistant", LEGENDA)
    await db.commit()
    logger.bind(phone=phone).info("Cursilho: clique no botão → vídeo enviado")
