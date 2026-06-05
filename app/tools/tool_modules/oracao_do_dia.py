"""Tool: oracao_do_dia — calendário de oração corporativo.

Distingue-se de `pedido_oracao` (pedido pessoal pra fila pastoral).

Use quando a pessoa quer orar JUNTO com a igreja pelo tema do dia.
Gera link autenticado (uso único, 30 min) + envia card visual.
"""
from __future__ import annotations

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import diacon_client
from app.services.deps import get_uaz_client


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
    title = theme.get("title", "")
    description = theme.get("description", "")

    # Monta mensagem
    if title:
        mensagem = (
            f"🙏 *Oração do dia: {title}*\n\n"
            f"{description}\n\n"
            f"Toque pra orar com a gente: {link}\n"
            f"_(link válido por 30 minutos)_"
        )
    else:
        mensagem = (
            "🙏 *Hoje vamos orar em unidade.*\n\n"
            f"Toque pra ver o motivo e registrar sua oração: {link}\n"
            f"_(link válido por 30 minutos)_"
        )

    # Envia card de imagem se disponível
    uaz = get_uaz_client()
    if image_url:
        try:
            await uaz.send_media(
                target_phone, image_url, type="image", text=mensagem
            )
            logger.info(f"oracao_do_dia: card enviado para {target_phone}")
            return "Link de oração enviado com o card do dia."
        except Exception:
            logger.exception("Falha ao enviar card de oração")

    # Fallback: só texto
    try:
        await uaz.send_text(target_phone, mensagem)
        return "Link de oração enviado."
    except Exception:
        logger.exception("Falha ao enviar link de oração")
        return f"Link gerado mas não consegui enviar: {link}"
