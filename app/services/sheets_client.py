"""Cliente Google Sheets.

Estratégia:
- Se `N8N_GOOGLE_WEBHOOK_URL` estiver setado → todas as chamadas vão para o n8n proxy.
- Caso contrário → fallback para Service Account local (googleapiclient).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.services import n8n_google_proxy

_service = None


def _get_service():
    """Lazy init do serviço Google Sheets (Service Account)."""
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
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    _service = build("sheets", "v4", credentials=creds, cache_discovery=False)
    logger.info("Google Sheets client inicializado (SA local)")
    return _service


def _rows_to_dicts(values: list[list[str]]) -> list[dict[str, Any]]:
    if len(values) < 2:
        return []
    headers = [h.strip() for h in values[0]]
    rows = []
    for i, row in enumerate(values[1:], start=2):
        padded = list(row) + [""] * (len(headers) - len(row))
        row_dict = {headers[j]: padded[j] for j in range(len(headers))}
        row_dict["_row_number"] = i
        rows.append(row_dict)
    return rows


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
def read_all(
    sheet_id: str,
    range_name: str = "A1:Z",
) -> list[dict[str, Any]]:
    """Lê todas as linhas de uma aba e retorna como lista de dicts (header = 1ª linha)."""
    if n8n_google_proxy.is_enabled():
        try:
            data = n8n_google_proxy.call(
                "sheets.read",
                {"sheet_id": sheet_id, "range": range_name},
            )
            values = data if isinstance(data, list) else data.get("values", [])
            return _rows_to_dicts(values)
        except Exception as e:
            logger.warning(f"Proxy n8n falhou em sheets.read, retornando vazio: {e}")
            return []

    service = _get_service()
    if service is None:
        logger.warning("Sheets client não disponível, retornando vazio")
        return []

    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=sheet_id, range=range_name)
        .execute()
    )
    return _rows_to_dicts(result.get("values", []))


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
def append_row(
    sheet_id: str,
    range_name: str,
    values: list[str | int | float],
) -> dict:
    """Adiciona uma linha ao final da planilha."""
    if n8n_google_proxy.is_enabled():
        try:
            return n8n_google_proxy.call(
                "sheets.append",
                {"sheet_id": sheet_id, "range": range_name, "values": values},
            ) or {}
        except Exception as e:
            logger.warning(f"Proxy n8n falhou em sheets.append: {e}")
            return {}

    service = _get_service()
    if service is None:
        logger.warning("Sheets client não disponível, append ignorado")
        return {}

    body = {"values": [values]}
    result = (
        service.spreadsheets()
        .values()
        .append(
            spreadsheetId=sheet_id,
            range=range_name,
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body,
        )
        .execute()
    )
    logger.debug(f"Sheets append: {result.get('updates', {}).get('updatedRows', 0)} rows")
    return result


def read_cell(
    sheet_id: str,
    range_name: str,
) -> str | None:
    """Lê uma única célula."""
    if n8n_google_proxy.is_enabled():
        try:
            data = n8n_google_proxy.call(
                "sheets.read_cell",
                {"sheet_id": sheet_id, "range": range_name},
            )
            if isinstance(data, str):
                return data
            if isinstance(data, dict):
                return data.get("value")
            return None
        except Exception as e:
            logger.warning(f"Proxy n8n falhou em sheets.read_cell: {e}")
            return None

    service = _get_service()
    if service is None:
        return None

    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=sheet_id, range=range_name)
        .execute()
    )
    values = result.get("values", [])
    if values and values[0]:
        return values[0][0]
    return None


def update_cell(
    sheet_id: str,
    range_name: str,
    value: str,
) -> dict:
    """Atualiza uma única célula."""
    if n8n_google_proxy.is_enabled():
        try:
            return n8n_google_proxy.call(
                "sheets.update",
                {"sheet_id": sheet_id, "range": range_name, "value": value},
            ) or {}
        except Exception as e:
            logger.warning(f"Proxy n8n falhou em sheets.update: {e}")
            return {}

    service = _get_service()
    if service is None:
        return {}

    body = {"values": [[value]]}
    return (
        service.spreadsheets()
        .values()
        .update(
            spreadsheetId=sheet_id,
            range=range_name,
            valueInputOption="USER_ENTERED",
            body=body,
        )
        .execute()
    )
