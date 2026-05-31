"""Tool: PAES_listar_arquivos — lista arquivos de divulgação do Drive."""
from __future__ import annotations

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services import drive_client


async def execute(
    args: dict,
    phone: str,
    db: AsyncSession,
) -> str:
    nome = args.get("nome", "").strip()
    if not nome:
        return "Erro: 'nome' é obrigatório para buscar arquivos."

    try:
        files = drive_client.search(
            nome,
            folder_id=settings.drive_folder_media,
        )
    except Exception:
        logger.exception("Erro ao buscar arquivos no Drive")
        return "Erro ao acessar o Google Drive."

    if not files:
        return f"Nenhum arquivo encontrado com o nome '{nome}'."

    lines = [f"Encontrados {len(files)} arquivo(s):"]
    for f in files:
        mime = f.get("mimeType", "")
        tipo = "📷 Imagem" if "image" in mime else "🎥 Vídeo" if "video" in mime else "📄 Documento"
        lines.append(f"  {tipo} — {f['name']}")

    return "\n".join(lines)
