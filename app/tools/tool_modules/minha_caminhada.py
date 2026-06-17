"""Tool: minha_caminhada — retrato de engajamento do membro (GET /members/stats).

A Diacon devolve um campo `text` já montado (saudação + números do ano +
janela de 30 dias + destaque + resumo de saúde), pronto pra enviar.
Use quando a pessoa quer saber da própria caminhada: frequência, orações,
streaks, "como estou indo".
"""
from __future__ import annotations

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import diacon_client


async def execute(args: dict, phone: str, db: AsyncSession) -> str:
    target_phone = args.get("telefone") or args.get("phone") or phone
    if not target_phone:
        return "Erro: 'telefone' é obrigatório."

    if not diacon_client.is_enabled():
        return "Erro: integração Diacon não configurada."

    try:
        data = await diacon_client.member_stats(target_phone)
    except diacon_client.DiaconError as e:
        logger.warning(f"minha_caminhada: {e.code} {e}")
        return "Não consegui buscar sua caminhada agora. Tenta de novo daqui a pouco."

    if not data.get("found"):
        return (
            "Ainda não encontrei você como membro pra montar esse resumo. "
            "Se já faz parte da igreja, confirma comigo seu cadastro que eu ajeito."
        )

    texto = (data.get("text") or "").strip()
    if not texto:
        return (
            "Você ainda não tem dados suficientes pra um resumo da caminhada. "
            "Continue participando que logo logo monto esse retrato pra você! 🙏"
        )

    return texto
