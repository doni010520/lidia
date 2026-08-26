"""Tool: oracao_do_dia — calendário/mural de oração corporativo.

Distingue-se de `pedido_oracao` (pedido pessoal pra fila pastoral).

Use quando a pessoa quer orar JUNTO com a igreja pelo tema do dia.
Gera link autenticado (uso único) + envia card visual.

Mudanças de UX (agosto/2026)
----------------------------
1. O MOTIVO DO DIA VAI NO CORPO DA MENSAGEM.
   Parte do público tem pacote de dados que só cobre WhatsApp. Se o texto
   da oração só existe dentro da página, essa pessoa simplesmente não ora.
   Agora ela consegue orar sem abrir nada; a página fica opcional, para
   quem quiser registrar.

2. AS ALVORADAS VÃO JUNTO, NO MESMO ENVIO.
   Antes o agente perguntava "você quer o mural ou a alvorada?" e cobrava
   um turno extra de quem já tinha sido específico. Mandar os dois de uma
   vez elimina a pergunta e o turno.

Chamada normalmente pelo `oracao_router` (em código, antes do LLM), mas
continua registrada como tool para os casos que escapam da regra.
"""
from __future__ import annotations

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services import diacon_client
from app.services.deps import get_uaz_client


def _rodape_alvoradas() -> str:
    """Bloco compacto das Alvoradas, anexado ao mural."""
    if not settings.oracao_incluir_alvoradas:
        return ""

    from app.services.oracao_router import alvoradas_texto

    bloco = alvoradas_texto(compacto=True)
    if not bloco:
        return ""
    return (
        "\n\n────────────\n"
        "Se preferir orar ao vivo com a gente, essas são as nossas Alvoradas:\n"
        f"{bloco}"
    )


def _monta_mensagem(link: str, theme: dict) -> str:
    titulo = (theme or {}).get("title") or ""
    descricao = (theme or {}).get("description") or ""

    partes: list[str] = []

    if titulo:
        partes.append(f"🙏 *Oração do dia: {titulo}*")
    else:
        partes.append("🙏 *Hoje vamos orar em unidade.*")

    # Motivo no corpo: quem não tem dados para abrir página já consegue orar.
    if descricao:
        partes.append(descricao)

    if link:
        partes.append(f"Toque aqui pra registrar sua oração no mural:\n{link}")

    return "\n\n".join(partes) + _rodape_alvoradas()


async def execute(args: dict, phone: str, db: AsyncSession) -> str:
    target_phone = args.get("telefone") or args.get("phone") or phone
    if not target_phone:
        return "Erro: 'telefone' é obrigatório."

    if not diacon_client.is_enabled():
        return "Erro: integração Diacon não configurada."

    try:
        data = await diacon_client.oracao_link(target_phone)
    except diacon_client.DiaconError as e:
        logger.warning(f"oracao_do_dia: {e.code} {e}")
        if e.code == "not_found":
            return (
                "Você ainda não está cadastrado como membro. "
                "Peça pra alguém da igreja te cadastrar primeiro."
            )
        if e.code == "bad_request":
            return "Telefone inválido."
        return "Não consegui gerar o link de oração agora. Tenta de novo daqui a pouco."

    link = data.get("link", "")
    image_url = data.get("image_url", "")
    theme = data.get("theme") or {}

    mensagem = _monta_mensagem(link, theme)

    uaz = get_uaz_client()

    # Card de imagem quando disponível (mensagem vai como legenda)
    if image_url:
        try:
            await uaz.send_media(
                target_phone, image_url, type="image", text=mensagem
            )
            logger.info(f"oracao_do_dia: card + alvoradas enviados para {target_phone}")
            return "Mural da oração do dia enviado com o card e os horários das Alvoradas."
        except Exception:
            logger.exception("Falha ao enviar card de oração")

    # Fallback: só texto
    try:
        await uaz.send_text(target_phone, mensagem)
        logger.info(f"oracao_do_dia: texto enviado para {target_phone}")
        return "Mural da oração do dia enviado com os horários das Alvoradas."
    except Exception:
        logger.exception("Falha ao enviar link de oração")
        return f"Link gerado mas não consegui enviar: {link}"
