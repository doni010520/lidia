"""Tool: resposta_oracao — registra pedido de oração na fila."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services import sheets_client

_SP_TZ = ZoneInfo("America/Sao_Paulo")


async def execute(
    args: dict,
    phone: str,
    db: AsyncSession,
) -> str:
    nome = args.get("Nome", args.get("nome", ""))
    telefone = args.get("Telefone", args.get("telefone", phone))
    encorajamento = args.get("Encorajamento", args.get("encorajamento", "sem palavra de encorajamento"))

    if not nome:
        return "Erro: 'Nome' é obrigatório."

    now = datetime.now(_SP_TZ).strftime("%d/%m/%Y %H:%M")

    # 1. Registrar no Sheets de oração
    if settings.sheets_log_oracao_id:
        try:
            sheets_client.append_row(
                settings.sheets_log_oracao_id,
                "A1",
                [nome, telefone, encorajamento, now, "", "false"],
                # Colunas: Nome, Telefone, Encorajamento, Data, Resposta, Enviado
            )
        except Exception:
            logger.exception("Erro ao registrar oração no Sheets")
            return "Erro ao registrar o pedido de oração."

    # 2. Notificar equipe Pastoral via notificar_time_interno
    from app.tools.tool_modules.notificar_time_interno import execute as notificar

    await notificar(
        {
            "tipo_situacao": "Pedido de oração",
            "prioridade": "media",
            "equipe_responsavel": "Oração",
            "nome": nome,
            "telefone": telefone,
            "detalhes": f"Encorajamento solicitado: {encorajamento}",
        },
        phone,
        db,
    )

    logger.bind(phone=telefone).info(f"Pedido de oração registrado: {nome}")
    return (
        "Pedido de oração registrado com sucesso. "
        "Nossa equipe pastoral vai interceder por você e retornaremos em breve. 🙏"
    )
