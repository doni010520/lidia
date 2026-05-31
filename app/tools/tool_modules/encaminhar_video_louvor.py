"""Tool: encaminhar_video_louvor — encaminha vídeo para a equipe de louvor."""
from __future__ import annotations

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.equipes import EquipeResponsavel
from app.services import drive_client
from app.services.deps import get_uaz_client


async def execute(
    args: dict,
    phone: str,
    db: AsyncSession,
) -> str:
    drive_file_id = args.get("drive_file_id", "")
    nome = args.get("nome", "")
    telefone = args.get("telefone", phone)

    if not drive_file_id:
        return "Erro: 'drive_file_id' é obrigatório."

    # Buscar equipe de louvor
    result = await db.execute(
        select(EquipeResponsavel).where(EquipeResponsavel.equipe.ilike("%louvor%"))
    )
    equipe = result.scalar_one_or_none()

    if not equipe or not equipe.telefones_responsaveis:
        return "Equipe de Louvor não encontrada ou sem responsáveis cadastrados."

    # Gerar URL do vídeo
    video_url = drive_client.get_view_url(drive_file_id)

    # Montar mensagem
    msg = (
        f"🎶 *Vídeo do Ministério de Louvor*\n\n"
        f"Enviado por: {nome} ({telefone})\n"
        f"Link do vídeo: {video_url}"
    )

    uaz = get_uaz_client()
    sent_to = []

    for resp_phone in equipe.telefones_responsaveis:
        try:
            await uaz.send_text(resp_phone, msg)
            sent_to.append(resp_phone)
        except Exception:
            logger.exception(f"Erro ao encaminhar vídeo para {resp_phone}")

    if sent_to:
        logger.bind(phone=telefone).info(
            f"Vídeo de louvor encaminhado para {len(sent_to)} responsáveis"
        )
        return f"Vídeo encaminhado para {len(sent_to)} responsável(is) da equipe de Louvor."
    return "Erro ao encaminhar o vídeo. Nenhum responsável recebeu."
