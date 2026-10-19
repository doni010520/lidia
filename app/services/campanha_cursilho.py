"""Campanha 54º Cursilho Masculino (out/2026) — convite em 2 etapas.

1. `enviar_convite`: mensagem curta com botão (o clique já conta como interação
   pro WhatsApp, o que protege o número da LidIA no disparo).
2. `responder_clique`: quem clica recebe o conteúdo da rodada.

Rodadas:
- "video" (13-14/10): "Quero saber" → vídeo do Bispo com o convite e o link.
- "texto" (19/10): "Quero ver" → texto da série Igreja em Movimento com o link.

As duas etapas vão pro histórico (`messages`), então se a pessoa responder
digitando em vez de clicar, a LidIA sabe do que se trata.
"""
from __future__ import annotations

from dataclasses import dataclass

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.conversation_service import save_message
from app.services.uaz_client import UAZClient

LINK = "https://sysigreja.com/Somos%20PAES/cursilho-masculino"


@dataclass(frozen=True)
class Rodada:
    botao_id: str
    botao_label: str
    convite: str  # {nome} = primeiro nome
    resposta: str
    video_url: str | None = None


RODADAS: dict[str, Rodada] = {
    "video": Rodada(
        botao_id="cursilho_quero",
        botao_label="Quero saber 🙏",
        convite=(
            "Oi, {nome}! 😊\n\n"
            "O Bispo Miguel Uchoa tem uma novidade pra você.\n\n"
            "Quer saber qual é?"
        ),
        resposta=(
            "Passando para te convocar a levar +1 para Cristo para o Cursilho Masculino, "
            "através da célula que você faz parte.\n\n"
            "Assista agora o vídeo que o Bispo Miguel Uchoa fez com muito carinho e "
            "veja o convite que ele faz.\n\n"
            "O 54º Cursilho Masculino será de 29 de outubro a 01 de novembro. "
            "Vamos levar +1 para Cristo.\n\n"
            "Segue o link para inscrição abaixo:\n\n"
            f"{LINK}"
        ),
        video_url="https://lidia.benitechlab.com/static/campanhas/cursilho-masculino.mp4",
    ),
    "texto": Rodada(
        botao_id="cursilho_ver",
        botao_label="Quero ver 🙏",
        convite=(
            "Oi, {nome}! 😊\n\n"
            "Tem uma mensagem especial sobre o Cursilho Masculino pra você.\n\n"
            "Quer ver?"
        ),
        resposta=(
            "O amor de Jesus vai ao encontro de quem se perdeu, procura até encontrar "
            "e o conduz de volta com alegria.\n\n"
            "A série Igreja em Movimento traz mais uma oportunidade para levantarmos e "
            "buscarmos mais 1 para Cristo através do Cursilho Masculino.\n\n"
            "Sua célula já está levando um homem para este Cursilho? Hoje é o dia para "
            "você inscrever +1 para Cristo.\n\n"
            "O 54º Cursilho Masculino será de 29 de outubro a 01 de novembro.\n\n"
            "Segue o link para inscrição abaixo:\n\n"
            f"{LINK}"
        ),
    ),
}

_POR_BOTAO = {r.botao_id: r for r in RODADAS.values()}


def _primeiro_nome(nome: str | None) -> str:
    return (nome or "").strip().split(" ")[0] if nome and nome.strip() else ""


async def enviar_convite(
    uaz: UAZClient, db: AsyncSession, phone: str, nome: str | None, rodada: str = "video",
) -> dict:
    r = RODADAS[rodada]
    primeiro = _primeiro_nome(nome)
    texto = r.convite.format(nome=primeiro) if primeiro else r.convite.replace("Oi, {nome}! ", "Oi! ")
    resp = await uaz._post("/send/menu", {
        "number": phone,
        "type": "button",
        "text": texto,
        "choices": [f"{r.botao_label}|{r.botao_id}"],
        "readchat": True,
    })
    await save_message(db, phone, "assistant", texto)
    await db.commit()
    logger.bind(phone=phone).info(f"Cursilho ({rodada}): convite com botão enviado")
    return resp


def eh_clique(button_id: str | None) -> bool:
    return button_id in _POR_BOTAO


async def responder_clique(uaz: UAZClient, db: AsyncSession, phone: str, button_id: str) -> None:
    r = _POR_BOTAO[button_id]
    await save_message(db, phone, "user", r.botao_label)
    if r.video_url:
        await uaz.send_media(phone, r.video_url, "video", text=r.resposta)
    else:
        await uaz.send_text(phone, r.resposta, link_preview=True)
    await save_message(db, phone, "assistant", r.resposta)
    await db.commit()
    logger.bind(phone=phone).info(f"Cursilho: clique em {button_id} → resposta enviada")
