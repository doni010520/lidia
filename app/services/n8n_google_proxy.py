"""Proxy para Google APIs via webhook n8n.

Quando `N8N_GOOGLE_WEBHOOK_URL` está configurado, todas as chamadas Google
(Sheets, Drive, Gmail) passam pelo n8n em vez de usar service account local.

Contrato HTTP:
    POST {N8N_GOOGLE_WEBHOOK_URL}
    Header: X-Lidia-Token: {N8N_GOOGLE_TOKEN}
    Body: {"action": "<verb>", "params": {...}}
    Resp: {"ok": true, "data": <result>}  OU  {"ok": false, "error": "..."}

Actions suportados:
    sheets.read      → params: {sheet_id, range}                 → list[list[str]]
    sheets.append    → params: {sheet_id, range, values}         → {updatedRows}
    sheets.read_cell → params: {sheet_id, range}                 → str | None
    sheets.update    → params: {sheet_id, range, value}          → {}
    drive.search     → params: {query, folder_id?, max_results}  → list[file]
    drive.list       → params: {folder_id, max_results}          → list[file]
    drive.upload     → params: {filename, mimetype, folder_id?,
                                content_b64}                     → {id}
    drive.download   → params: {file_id}                         → {content_b64, mimetype, name}
    gmail.send       → params: {to, subject, body, from?}        → {id}
"""
from __future__ import annotations

from typing import Any

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings


class N8nProxyError(RuntimeError):
    """Falha na chamada ao webhook n8n."""


def is_enabled() -> bool:
    return bool(settings.n8n_google_webhook_url)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8), reraise=True)
def call(action: str, params: dict[str, Any] | None = None) -> Any:
    """Chamada síncrona ao webhook n8n."""
    if not is_enabled():
        raise N8nProxyError("N8N_GOOGLE_WEBHOOK_URL não configurado")

    headers = {"Content-Type": "application/json"}
    if settings.n8n_google_token:
        headers["X-Lidia-Token"] = settings.n8n_google_token

    payload = {"action": action, "params": params or {}}

    try:
        with httpx.Client(timeout=settings.n8n_google_timeout_seconds) as client:
            resp = client.post(
                settings.n8n_google_webhook_url,
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            body = resp.json()
    except httpx.HTTPError as e:
        logger.error(f"n8n proxy HTTP error em {action}: {e}")
        raise N8nProxyError(str(e)) from e

    if isinstance(body, dict) and body.get("ok") is False:
        err = body.get("error", "erro desconhecido")
        logger.error(f"n8n proxy retornou erro em {action}: {err}")
        raise N8nProxyError(err)

    # n8n geralmente devolve {ok:true, data:...} mas aceita formato cru também
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body


async def acall(action: str, params: dict[str, Any] | None = None) -> Any:
    """Versão async — usa httpx.AsyncClient."""
    if not is_enabled():
        raise N8nProxyError("N8N_GOOGLE_WEBHOOK_URL não configurado")

    headers = {"Content-Type": "application/json"}
    if settings.n8n_google_token:
        headers["X-Lidia-Token"] = settings.n8n_google_token

    payload = {"action": action, "params": params or {}}

    try:
        async with httpx.AsyncClient(timeout=settings.n8n_google_timeout_seconds) as client:
            resp = await client.post(
                settings.n8n_google_webhook_url,
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            body = resp.json()
    except httpx.HTTPError as e:
        logger.error(f"n8n proxy HTTP error em {action}: {e}")
        raise N8nProxyError(str(e)) from e

    if isinstance(body, dict) and body.get("ok") is False:
        err = body.get("error", "erro desconhecido")
        logger.error(f"n8n proxy retornou erro em {action}: {err}")
        raise N8nProxyError(err)

    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body
