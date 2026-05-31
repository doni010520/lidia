"""Cliente Google Sheets via Service Account.

Operações:
- read_all(sheet_id, range): lê todas as linhas como lista de dicts
- append_row(sheet_id, range, values): adiciona uma linha ao final
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings

_service = None


def _get_service():
    """Lazy init do serviço Google Sheets."""
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
    logger.info("Google Sheets client inicializado")
    return _service


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
def read_all(
    sheet_id: str,
    range_name: str = "A1:Z",
) -> list[dict[str, Any]]:
    """Lê todas as linhas de uma aba e retorna como lista de dicts.

    A primeira linha é tratada como cabeçalho.
    """
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
    values = result.get("values", [])
    if len(values) < 2:
        return []

    headers = [h.strip() for h in values[0]]
    rows = []
    for i, row in enumerate(values[1:], start=2):
        # Preencher colunas faltantes com string vazia
        padded = row + [""] * (len(headers) - len(row))
        row_dict = {headers[j]: padded[j] for j in range(len(headers))}
        row_dict["_row_number"] = i  # rastreio de qual linha veio
        rows.append(row_dict)

    return rows


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
def append_row(
    sheet_id: str,
    range_name: str,
    values: list[str | int | float],
) -> dict:
    """Adiciona uma linha ao final da planilha."""
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
