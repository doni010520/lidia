"""Tool: parar_comunicados — "não quero mais receber" dito na conversa.

Grava allow_contact=false na Diacon (guia §5b): a pessoa sai na hora da lista
de comunicados e de todo envio seguinte. Só confirma depois do 200; o
_request_json já repete 5xx. Telefone sempre do remetente.
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
        resp = await diacon_client.member_update(phone=target_phone, allow_contact=False)
    except diacon_client.DiaconError as e:
        logger.warning(f"parar_comunicados: {e.status} {e.code} {e}")
        if e.status == 404 or e.code == "not_found":
            return (
                "Esse telefone não tem cadastro na igreja, então não está na lista de "
                "comunicados. Diga à pessoa que ela não vai receber."
            )
        return (
            "NÃO deu certo registrar o pedido agora. Não diga que está feito: peça "
            "desculpas e para ela tentar de novo daqui a pouco."
        )
    if resp.get("contact_choice") == "refusal_kept":
        return "A pessoa já estava fora da lista (tinha pedido pelo formulário/perfil). Confirme que ela não recebe."
    logger.bind(phone=target_phone).info("parar_comunicados: allow_contact=false")
    return "Pronto: a pessoa saiu da lista e não recebe mais comunicados. Confirme com carinho, numa frase."
