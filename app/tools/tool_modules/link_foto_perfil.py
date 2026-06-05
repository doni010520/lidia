"""Tool: link_foto_perfil — manda link pra membro adicionar/atualizar foto.

Link autenticado de uso único (30 min) — pessoa cai direto na tela
de envio sem precisar de código.
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
        data = await diacon_client.member_photo_link(target_phone)
    except diacon_client.DiaconError as e:
        logger.warning(f"link_foto_perfil: {e.code} {e}")
        if e.code == "not_found":
            return (
                "Esse telefone ainda não é membro cadastrado. "
                "Quer que eu cadastre primeiro?"
            )
        if e.code == "forbidden":
            return "Esse cadastro está inativo. Procure a secretaria da igreja."
        if e.code == "bad_request":
            return "Telefone inválido."
        return "Não consegui gerar o link agora. Tenta de novo em alguns segundos."

    link = data.get("link", "")
    has_photo = data.get("has_photo", False)
    first_name = (data.get("member") or {}).get("first_name", "")

    saudacao = f"Oi {first_name}! " if first_name else "Oi! "
    if has_photo:
        msg = (
            f"{saudacao}Quer atualizar sua foto de perfil? "
            f"É só tocar aqui: {link}\n_(link válido por 30 minutos)_"
        )
    else:
        msg = (
            f"{saudacao}Pra adicionar sua foto, toque aqui: {link}\n"
            f"_(link válido por 30 minutos)_"
        )

    try:
        uaz = get_uaz_client()
        await uaz.send_text(target_phone, msg)
        return f"Link de foto enviado para {target_phone}."
    except Exception:
        logger.exception("Falha ao enviar link de foto")
        return f"Link gerado mas não consegui enviar: {link}"
