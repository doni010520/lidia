"""Campanha 54º Cursilho Masculino (out/2026) — convite em 2 etapas.

1. `enviar_convite`: mensagem curta com botão (o clique já conta como interação
   pro WhatsApp, o que protege o número da LidIA no disparo).
2. `responder_clique`: quem clica recebe o conteúdo da rodada.

Rodadas:
- "video" (13-14/10): "Quero saber" → vídeo do Bispo com o convite e o link.
- "texto" (19/10): "Quero ver" → cartaz com o texto da série Igreja em Movimento e o link.

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
    imagem_url: str | None = None
    # 2º botão "Não quero receber": grava allow_contact=false na Diacon
    # (guia Diacon §5b). Só em comunicado pra base toda.
    com_saida: bool = False


# Botão de saída comum a todos os comunicados. WhatsApp corta título de
# botão acima de 20 caracteres.
SAIR_ID = "comunicado_sair"
SAIR_LABEL = "Não quero receber"
_SAIR_OK = (
    "Tudo bem{nome}! Você não vai mais receber nossos comunicados por aqui. "
    "Se mudar de ideia, é só me avisar 🙏"
)
_SAIR_MANTIDA = (
    "Você tinha pedido pra não receber pelo formulário ou pelo seu perfil, "
    "então continua fora da lista. Pra voltar, é por lá mesmo 🙏"
)
_SAIR_FALHOU = (
    "Não consegui registrar seu pedido agora. Pode clicar de novo daqui a "
    "pouco? Desculpa o incômodo 🙏"
)


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
        imagem_url="https://lidia.benitechlab.com/static/campanhas/cursilho-cartaz.jpg",
    ),
    # Devocional 2027 (nov/2026): base toda de membros que aceitam receber.
    "devocional": Rodada(
        botao_id="devocional_ver",
        botao_label="Quero ver 🎁",
        convite=(
            "Oi, {nome}! 😊\n\n"
            "O Arcebispo Miguel preparou um presente pra você começar 2027 com Jesus.\n\n"
            "Quer ver?"
        ),
        resposta=(
            "📖 *A cada Manhã com os Evangelhos*\n"
            "_O devocional de 2027 do nosso querido Arcebispo Miguel Uchoa_\n\n"
            "Que tal começar cada manhã do próximo ano com Jesus?\n\n"
            "São *365 devocionais*, um para cada dia de 2027. Cada leitura parte de um "
            "trecho dos Evangelhos, traz uma reflexão curta e termina com um "
            "*\"Para lembrar\"*: uma frase para levar com você ao longo do dia.\n\n"
            "✨ Um tema para cada mês\n"
            "📕 Capa dura, 400 páginas\n"
            "🎁 Um ótimo presente para a família, a célula e os amigos, natal está "
            "chegando e é melhor que meias\n\n"
            "Os livros ainda estão a caminho. *Reserve agora e garanta o seu.* A data "
            "da retirada na PAES Store e/ou secretaria será divulgada assim que eles "
            "chegarem.\n\n"
            "👉 Reserve pelo link:\n"
            "https://diacon.ia.br/loja/paes-catedral/p/devocional-2027-a-cada-manha-com-os-evangelhos"
        ),
        imagem_url="https://lidia.benitechlab.com/static/campanhas/devocional-2027.jpg",
        com_saida=True,
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
    choices = [f"{r.botao_label}|{r.botao_id}"]
    if r.com_saida:
        choices.append(f"{SAIR_LABEL}|{SAIR_ID}")
    resp = await uaz._post("/send/menu", {
        "number": phone,
        "type": "button",
        "text": texto,
        "choices": choices,
        "readchat": True,
    })
    await save_message(db, phone, "assistant", texto)
    await db.commit()
    logger.bind(phone=phone).info(f"Campanha ({rodada}): convite com botão enviado")
    return resp


def eh_clique(button_id: str | None) -> bool:
    return button_id in _POR_BOTAO or button_id == SAIR_ID


async def _registrar_saida(uaz: UAZClient, db: AsyncSession, phone: str) -> None:
    """Clique em "Não quero receber": allow_contact=false na Diacon.

    Só confirma à pessoa depois do 200 (guia §5b). O _request_json já repete
    5xx; se ainda assim falhar, pede pra ela tentar de novo.
    """
    from app.services import diacon_client

    await save_message(db, phone, "user", SAIR_LABEL)
    try:
        resp = await diacon_client.member_update(phone=phone, allow_contact=False)
        if resp.get("contact_choice") == "refusal_kept":
            texto = _SAIR_MANTIDA
        else:
            nome = ((resp.get("member") or {}).get("first_name") or "").strip()
            texto = _SAIR_OK.format(nome=f", {nome}" if nome else "")
        logger.bind(phone=phone).info("Campanha: saída registrada (allow_contact=false)")
    except diacon_client.DiaconError as e:
        logger.warning(f"Campanha: falha ao registrar saída de {phone}: {e.status} {e}")
        texto = _SAIR_FALHOU
    await uaz.send_text(phone, texto)
    await save_message(db, phone, "assistant", texto)
    await db.commit()


async def responder_clique(uaz: UAZClient, db: AsyncSession, phone: str, button_id: str) -> None:
    if button_id == SAIR_ID:
        await _registrar_saida(uaz, db, phone)
        return
    r = _POR_BOTAO[button_id]
    await save_message(db, phone, "user", r.botao_label)
    if r.video_url:
        await uaz.send_media(phone, r.video_url, "video", text=r.resposta)
    elif r.imagem_url:
        await uaz.send_media(phone, r.imagem_url, "image", text=r.resposta)
    else:
        await uaz.send_text(phone, r.resposta, link_preview=True)
    await save_message(db, phone, "assistant", r.resposta)
    await db.commit()
    logger.bind(phone=phone).info(f"Cursilho: clique em {button_id} → resposta enviada")
