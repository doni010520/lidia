"""Cliente Google Drive.

Estratégia:
- Se `N8N_GOOGLE_WEBHOOK_URL` estiver setado → chamadas vão para o n8n proxy.
- Caso contrário → fallback para Service Account local.
"""
from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Any

from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.services import n8n_google_proxy

_service = None


def _get_service():
    """Lazy init do serviço Google Drive (SA local)."""
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
    logger.info("Google Drive client inicializado (SA local)")
    return _service


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
def search(
    query: str,
    folder_id: str | None = None,
    *,
    max_results: int = 20,
) -> list[dict[str, Any]]:
    """Busca arquivos no Drive por nome (contains, case-insensitive)."""
    if n8n_google_proxy.is_enabled():
        try:
            data = n8n_google_proxy.call(
                "drive.search",
                {"query": query, "folder_id": folder_id, "max_results": max_results},
            )
            return data if isinstance(data, list) else data.get("files", [])
        except Exception as e:
            logger.warning(f"Proxy n8n falhou em drive.search: {e}")
            return []

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
    if n8n_google_proxy.is_enabled():
        try:
            data = n8n_google_proxy.call(
                "drive.list",
                {"folder_id": folder_id, "max_results": max_results},
            )
            return data if isinstance(data, list) else data.get("files", [])
        except Exception as e:
            logger.warning(f"Proxy n8n falhou em drive.list: {e}")
            return []

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
    if n8n_google_proxy.is_enabled():
        b64 = base64.b64encode(content).decode("ascii")
        try:
            data = n8n_google_proxy.call(
                "drive.upload",
                {
                    "filename": filename,
                    "mimetype": mimetype,
                    "folder_id": folder_id,
                    "content_b64": b64,
                },
            )
            file_id = data.get("id") if isinstance(data, dict) else data
            if not file_id:
                raise RuntimeError("Proxy n8n não retornou file_id")
            logger.info(f"Drive upload (n8n): {filename} → {file_id}")
            return file_id
        except Exception as e:
            logger.error(f"Proxy n8n falhou em drive.upload: {e}")
            raise

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

    try:
        service.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"},
        ).execute()
    except Exception:
        logger.warning(f"Falha ao compartilhar {file_id} publicamente")

    return file_id


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
def download_file(file_id: str) -> tuple[bytes, str, str]:
    """Baixa um arquivo do Drive. Retorna (content_bytes, mimetype, name)."""
    if n8n_google_proxy.is_enabled():
        try:
            data = n8n_google_proxy.call("drive.download", {"file_id": file_id})
            if not isinstance(data, dict):
                raise RuntimeError("Resposta inválida do proxy n8n")
            content_b64 = data.get("content_b64", "")
            return (
                base64.b64decode(content_b64),
                data.get("mimetype", "application/octet-stream"),
                data.get("name", file_id),
            )
        except Exception as e:
            logger.error(f"Proxy n8n falhou em drive.download: {e}")
            raise

    service = _get_service()
    if service is None:
        raise RuntimeError("Drive client não disponível")

    from googleapiclient.http import MediaIoBaseDownload

    meta = service.files().get(fileId=file_id, fields="name, mimeType").execute()
    request = service.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue(), meta.get("mimeType", "application/octet-stream"), meta.get("name", file_id)


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
