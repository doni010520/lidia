"""Tool: novos_convertidos — registra decisão por Cristo no Diacon.

Diacon = fonte de verdade. Vai como POST /pastoral com area='decision'.
"""
from __future__ import annotations

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import diacon_client


async def execute(args: dict, phone: str, db: AsyncSession) -> str:
    telefone = args.get("telefone") or phone
    nome = (args.get("nome") or "").strip()

    if not nome:
        return "Erro: 'nome' é obrigatório."

    if not diacon_client.is_enabled():
        return "Erro: integração Diacon não configurada."

    try:
        resp = await diacon_client.pastoral_create(
            area="decision",
            title=f"Decisão por Cristo — {nome}",
            context="Registrado pela LidIA no WhatsApp.",
            priority="high",
            phone=telefone,
            name=nome,
        )
    except diacon_client.DiaconError as e:
        logger.warning(f"novos_convertidos: Diacon {e.code} {e}")
        return f"Não consegui registrar agora ({e.code or 'erro'}). Tenta de novo em alguns segundos."

    # Write-behind local
    try:
        await db.execute(
            text(
                "INSERT INTO novos_convertidos (telefone, nome) "
                "VALUES (:t, :n) ON CONFLICT (telefone) DO NOTHING"
            ),
            {"t": telefone, "n": nome},
        )
        await db.commit()
    except Exception:
        logger.exception("novos_convertidos: write-behind falhou (não crítico)")

    logger.bind(phone=telefone).info(
        f"Decisão por Cristo registrada no Diacon: id={resp.get('id')}"
    )
    return (
        f"Decisão por Cristo registrada com sucesso para {nome}. "
        "Glória a Deus! 🙏 A equipe pastoral vai te acompanhar."
    )
