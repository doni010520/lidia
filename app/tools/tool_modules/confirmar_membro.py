"""Tool: confirmar_membro — a própria pessoa passa de visitante a membro.

Caso que originou (23/10/26, Myrian): veio do cadastro importado como
visitante, frequenta a célula, disse à LidIA "estou como visitante"; a LidIA
só avisava a equipe e o cadastro ficava errado.

Regras (guia Diacon §5): o teto do bot é visitante ↔ membro — cargo e
consentimentos ficam no painel. O telefone é SEMPRE o do remetente, então
ninguém altera o cadastro de outra pessoa. Só promove `visitor` → `active`;
inativo/pendente ficam com a secretaria.
"""
from __future__ import annotations

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import diacon_client
from app.tools.tool_modules._phone import resolve_phone


async def execute(args: dict, phone: str, db: AsyncSession) -> str:
    target_phone = resolve_phone(args.get("telefone"), phone)
    if not target_phone:
        return "Erro: não sei o telefone de quem está falando."
    if not diacon_client.is_enabled():
        return "Erro: integração Diacon não configurada."

    try:
        found = await diacon_client.member_lookup(target_phone)
    except diacon_client.DiaconError as e:
        logger.warning(f"confirmar_membro lookup: {e.code} {e}")
        return "Não consegui consultar o cadastro agora. Tenta de novo em alguns segundos."

    if not found.get("found"):
        return (
            "Esse telefone ainda não tem cadastro na igreja. Peça o nome completo "
            "e faça o cadastro com `cadastrar_contato` usando status 'membro'."
        )

    member = found.get("member") or {}
    first = member.get("first_name") or ""
    status = member.get("status")
    if status == "active":
        return f"{first} já está cadastrado(a) como membro. Nada a mudar."
    if status != "visitor":
        return (
            f"O cadastro de {first} está como '{status}', e essa mudança é feita "
            "pela secretaria. Ofereça encaminhar com `notificar_time_interno`."
        )

    try:
        await diacon_client.member_update(phone=target_phone, status="active")
    except diacon_client.DiaconError as e:
        logger.warning(f"confirmar_membro update: {e.code} {e}")
        return "Não consegui atualizar o cadastro agora. Tenta de novo em alguns segundos."

    logger.bind(phone=target_phone).info("confirmar_membro: visitante → membro")
    return f"Pronto: o cadastro de {first} foi atualizado de visitante para membro."
