"""Tool: PAES_download_arquivos — envia arquivos do Drive para o WhatsApp do usuário."""
from __future__ import annotations

import asyncio

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services import drive_client
from app.services.deps import get_uaz_client


async def execute(
    args: dict,
    phone: str,
    db: AsyncSession,
) -> str:
    arquivos = args.get("arquivos", [])
    telefone = args.get("telefone", phone)

    if not arquivos:
        return "Erro: 'arquivos' (lista de nomes) é obrigatório."

    uaz = get_uaz_client()
    sent = []
    errors = []

    for nome_arquivo in arquivos:
        try:
            files = drive_client.search(
                nome_arquivo,
                folder_id=settings.drive_folder_media,
                max_results=1,
            )
        except Exception:
            logger.exception(f"Erro ao buscar '{nome_arquivo}' no Drive")
            errors.append(nome_arquivo)
            continue

        if not files:
            errors.append(nome_arquivo)
            continue

        f = files[0]
        file_url = drive_client.get_public_url(f["id"])
        uaz_type = drive_client.detect_uaz_type(f.get("mimeType", ""))

        try:
            await uaz.send_media(
                telefone,
                file_url,
                uaz_type,
                text=f["name"],
            )
            sent.append(f["name"])
            await asyncio.sleep(1)
        except Exception:
            logger.exception(f"Erro ao enviar '{f['name']}' via WhatsApp")
            errors.append(nome_arquivo)

    parts = []
    if sent:
        parts.append(f"Enviados com sucesso: {', '.join(sent)}")
    if errors:
        parts.append(f"Não encontrados/erro: {', '.join(errors)}")

    return "\n".join(parts) if parts else "Nenhum arquivo processado."
