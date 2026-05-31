"""Cliente Google Drive via Service Account.

Operações:
- search(query, folder_id): busca arquivos por nome
- upload_bytes(content, filename, mimetype, folder_id): upload de bytes
- get_public_url(file_id): gera link público (viewable)
- list_files(folder_id): lista arquivos de uma pasta
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings

_service = None


def _get_service():
    """Lazy init do serviço Google Drive."""
    global _service
    if _service is not None:
        return _service

    sa_path = Path(settings.google_service_account_json)
    if not sa_path.exists():
        logger.warning(f"Service account não encontrada: {sa_path}")
        return None

    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_service_account_file(
        str(sa_path),
        scopes=["https://www.googleapis.com/auth/drive"],
    )
    _service = build("drive", "v3", credentials=creds, cache_discovery=False)
    logger.info("Google Drive client inicializado")
    return _service


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
def search(
    query: str,
    folder_id: str | None = None,
    *,
    max_results: int = 20,
) -> list[dict[str, Any]]:
    """Busca arquivos no Drive por nome (contains, case-insensitive)."""
    service = _get_service()
    if service is None:
        return []

    q_parts = [f"name contains '{query}'", "trashed = false"]
    if folder_id:
        q_parts.append(f"'{folder_id}' in parents")

    result = (
        service.files()
        .list(
            q=" and ".join(q_parts),
            fields="files(id, name, mimeType, webViewLink, webContentLink, size)",
            pageSize=max_results,
            orderBy="name",
        )
        .execute()
    )
    files = result.get("files", [])
    logger.debug(f"Drive search '{query}' → {len(files)} arquivos")
    return files


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
def list_files(
    folder_id: str,
    *,
    max_results: int = 50,
) -> list[dict[str, Any]]:
    """Lista arquivos de uma pasta do Drive."""
    service = _get_service()
    if service is None:
        return []

    result = (
        service.files()
        .list(
            q=f"'{folder_id}' in parents and trashed = false",
            fields="files(id, name, mimeType, webViewLink, webContentLink, size)",
            pageSize=max_results,
            orderBy="name",
        )
        .execute()
    )
    return result.get("files", [])


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
def upload_bytes(
    content: bytes,
    filename: str,
    mimetype: str,
    folder_id: str | None = None,
) -> str:
    """Upload de bytes para o Drive. Retorna file_id."""
    service = _get_service()
    if service is None:
        raise RuntimeError("Drive client não disponível")

    from googleapiclient.http import MediaIoBaseUpload

    file_metadata: dict[str, Any] = {"name": filename}
    if folder_id:
        file_metadata["parents"] = [folder_id]

    media = MediaIoBaseUpload(
        io.BytesIO(content),
        mimetype=mimetype,
        resumable=True,
    )

    file = (
        service.files()
        .create(body=file_metadata, media_body=media, fields="id")
        .execute()
    )
    file_id = file["id"]
    logger.info(f"Drive upload: {filename} → {file_id}")

    # Tornar publicamente acessível (anyone with link)
    try:
        service.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"},
        ).execute()
    except Exception:
        logger.warning(f"Falha ao compartilhar {file_id} publicamente")

    return file_id


def get_public_url(file_id: str) -> str:
    """Gera URL pública de download direto do Drive."""
    return f"https://drive.google.com/uc?export=download&id={file_id}"


def get_view_url(file_id: str) -> str:
    """Gera URL de visualização no Drive."""
    return f"https://drive.google.com/file/d/{file_id}/view"


_MIME_TO_UAZ_TYPE = {
    "image/jpeg": "image",
    "image/png": "image",
    "image/gif": "image",
    "image/webp": "image",
    "video/mp4": "video",
    "video/3gpp": "video",
    "video/quicktime": "video",
    "application/pdf": "document",
}


def detect_uaz_type(mimetype: str) -> str:
    """Mapeia MIME type do Drive para tipo da uazapi (image/video/document)."""
    return _MIME_TO_UAZ_TYPE.get(mimetype, "document")
