"""Tool: pedido_oracao — pedido pessoal pra fila pastoral (Céus Abertos).

Distingue-se de `oracao_do_dia` (oração corporativa pelo motivo do dia).

Use quando a pessoa quer que ALGUÉM ore POR ELA ou alguém querido.
Gravado em /oracao/pedido (Diacon = fila pastoral).
"""
from __future__ import annotations

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import diacon_client


async def execute(args: dict, phone: str, db: AsyncSession) -> str:
    pedido = (args.get("pedido") or args.get("request") or "").strip()
    nome = (args.get("nome") or args.get("name") or "").strip()
    tel = args.get("telefone") or args.get("phone") or phone

    if len(pedido) < 2:
        return "Erro: 'pedido' precisa ter pelo menos 2 caracteres."

    if not diacon_client.is_enabled():
        return "Erro: integração Diacon não configurada."

    try:
        data = await diacon_client.oracao_pedido(
            request=pedido[:2000], phone=tel, name=nome or None
        )
    except diacon_client.DiaconError as e:
        logger.warning(f"pedido_oracao: {e.code} {e}")
        return "Não consegui registrar o pedido agora. Tenta de novo em alguns segundos."

    logger.bind(phone=tel).info(
        f"Pedido de oração registrado em Diacon: id={data.get('id')}"
    )
    return (
        "🙏 Seu pedido foi registrado e a equipe pastoral foi avisada. "
        "Estamos orando por você. Que a paz de Cristo te console."
    )
