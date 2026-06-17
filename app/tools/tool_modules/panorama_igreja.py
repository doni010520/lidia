"""Tool: panorama_igreja — panorama gerencial (GET /admin/overview).

Só responde se o telefone for de um ADMINISTRADOR da igreja. A Diacon
devolve um campo `text` já montado (membros, células, último domingo,
check-ins, eventos, frequência, saúde), pronto pra enviar.
Use quando um admin pede os números da igreja.
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
        data = await diacon_client.admin_overview(target_phone)
    except diacon_client.DiaconError as e:
        logger.warning(f"panorama_igreja: {e.code} {e}")
        return "Não consegui buscar o panorama agora. Tenta de novo daqui a pouco."

    if not data.get("is_admin"):
        return (
            "Esse panorama é restrito à administração da igreja. "
            "Seu número não consta como administrador no sistema."
        )

    texto = (data.get("text") or "").strip()
    if not texto:
        return "O panorama veio vazio agora. Tenta de novo em alguns instantes."

    return texto
