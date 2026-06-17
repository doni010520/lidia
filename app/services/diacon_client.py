"""Cliente HTTP para a API Diacon (https://diacon.ia.br/api/v1/{igreja}).

Documentação: api-referencia.md (Diacon v1).

Características:
- async (httpx.AsyncClient)
- Header Authorization: Bearer <DIACON_TOKEN>
- Envelope padrão {"ok": bool, "error"?: str, "message"?: str, ...}
- Levanta DiaconError em 4xx/5xx, com type e mensagem útil
- Retry exponencial em 5xx e 429 (tenacity)
- get_pdf() para endpoints binários (cells/qr)
"""
from __future__ import annotations

from typing import Any

import httpx
from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings


class DiaconError(RuntimeError):
    """Erro na chamada à API Diacon."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        code: str | None = None,
        payload: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code  # 'not_found', 'forbidden', etc.
        self.payload = payload or {}


def _enabled() -> bool:
    return bool(settings.diacon_base_url and settings.diacon_token)


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.diacon_token}",
        "Accept": "application/json",
    }


def _base_url() -> str:
    return settings.diacon_base_url.rstrip("/")


def _raise_for_status(
    resp: httpx.Response, *, endpoint: str
) -> None:
    if resp.is_success:
        return
    body: dict[str, Any] = {}
    try:
        body = resp.json() if resp.content else {}
    except Exception:
        body = {"raw": resp.text[:500]}

    code = body.get("error") or ""
    msg = body.get("message") or resp.text[:300] or resp.reason_phrase
    logger.warning(
        f"Diacon {endpoint} → {resp.status_code} {code}: {msg[:200]}"
    )
    raise DiaconError(
        message=str(msg),
        status=resp.status_code,
        code=str(code) if code else None,
        payload=body,
    )


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, DiaconError):
        # Retry em 429 (rate_limited) e 5xx
        if exc.status and (exc.status == 429 or 500 <= exc.status < 600):
            return True
        return False
    # Retry em erros de rede transitórios
    return isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError))


@retry(
    retry=retry_if_exception_type((DiaconError, httpx.HTTPError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=1, max=8),
    reraise=True,
)
async def _request_json(
    method: str,
    path: str,
    *,
    params: dict | None = None,
    json_body: dict | None = None,
) -> dict[str, Any]:
    if not _enabled():
        raise DiaconError("Diacon não configurado (DIACON_BASE_URL/DIACON_TOKEN ausentes)")
    url = f"{_base_url()}/{path.lstrip('/')}"
    timeout = settings.diacon_timeout_seconds
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.request(
            method, url, headers=_headers(), params=params, json=json_body
        )
        _raise_for_status(resp, endpoint=f"{method} {path}")
        if not resp.content:
            return {"ok": True}
        try:
            data = resp.json()
        except Exception as e:
            raise DiaconError(
                f"Resposta não-JSON em {method} {path}: {e}", status=resp.status_code
            ) from e
        return data


# ── Helpers de alto nível ────────────────────────────────────────────────

def is_enabled() -> bool:
    """True se DIACON_BASE_URL e DIACON_TOKEN estão configurados."""
    return _enabled()


async def ping() -> dict[str, Any]:
    """GET /ping — valida o token e retorna escopos."""
    return await _request_json("GET", "ping")


# ── Members ──

async def member_lookup(phone: str) -> dict[str, Any]:
    """GET /members/lookup?phone=...

    Retorno: {ok, found, member?: {...}}
    """
    return await _request_json("GET", "members/lookup", params={"phone": phone})


async def member_create(
    *,
    full_name: str,
    phone: str | None = None,
    birth_date: str | None = None,
    email: str | None = None,
    gender: str | None = None,
    status: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """POST /members — idempotente por telefone."""
    body: dict[str, Any] = {"full_name": full_name}
    if phone:
        body["phone"] = phone
    if birth_date:
        body["birth_date"] = birth_date
    if email:
        body["email"] = email
    if gender:
        body["gender"] = gender
    if status:
        body["status"] = status
    if notes:
        body["notes"] = notes
    return await _request_json("POST", "members", json_body=body)


async def member_update(
    *,
    id: str | None = None,
    phone: str | None = None,
    **fields: Any,
) -> dict[str, Any]:
    """PATCH /members — identifica por id OU phone, atualiza campos."""
    if not id and not phone:
        raise DiaconError("member_update exige 'id' ou 'phone'")
    body: dict[str, Any] = {}
    if id:
        body["id"] = id
    if phone:
        body["phone"] = phone
    for k, v in fields.items():
        if v is not None:
            body[k] = v
    return await _request_json("PATCH", "members", json_body=body)


async def member_photo_link(phone: str) -> dict[str, Any]:
    """POST /members/photo-link — link de uso único (30 min)."""
    return await _request_json(
        "POST", "members/photo-link", json_body={"phone": phone}
    )


async def member_cells(phone: str) -> dict[str, Any]:
    """GET /members/cells?phone=... — diz se é líder + suas células."""
    return await _request_json("GET", "members/cells", params={"phone": phone})


async def member_stats(phone: str) -> dict[str, Any]:
    """GET /members/stats?phone=... — engajamento do membro.

    Retorno: {ok, found, member?, stats?, text?}. `text` é a mensagem
    pastoral já montada, pronta pra enviar.
    """
    return await _request_json("GET", "members/stats", params={"phone": phone})


# ── Cells ──

async def cells_near(lat: float, lng: float, *, limit: int = 5) -> dict[str, Any]:
    """GET /cells/near?lat=&lng=&limit="""
    return await _request_json(
        "GET", "cells/near", params={"lat": lat, "lng": lng, "limit": limit}
    )


async def cell_qr_pdf(phone: str, group_id: str | None = None) -> tuple[bytes, dict | None]:
    """GET /cells/qr — devolve (pdf_bytes, None) em sucesso,
    ou (b"", payload_json) quando precisa escolher group_id (400 com lista).

    Levanta DiaconError em 403 (não-líder) ou outros erros.
    """
    if not _enabled():
        raise DiaconError("Diacon não configurado")
    url = f"{_base_url()}/cells/qr"
    params: dict[str, Any] = {"phone": phone}
    if group_id:
        params["group_id"] = group_id
    async with httpx.AsyncClient(timeout=settings.diacon_timeout_seconds) as client:
        resp = await client.get(url, headers=_headers(), params=params)
        # 400 com lista de células pra escolher
        if resp.status_code == 400 and "application/json" in resp.headers.get("content-type", ""):
            try:
                body = resp.json()
            except Exception:
                _raise_for_status(resp, endpoint="GET cells/qr")
            if "cells" in body:
                return b"", body
            _raise_for_status(resp, endpoint="GET cells/qr")
        if not resp.is_success:
            _raise_for_status(resp, endpoint="GET cells/qr")
        return resp.content, None


async def cells_summary_pdf(
    phone: str, *, group_id: str | None = None, date: str | None = None
) -> tuple[bytes, dict | None]:
    """GET /cells/summary — PDF do resumo de presença de um encontro.

    Devolve (pdf_bytes, None) em sucesso, ou (b"", payload_json) quando
    precisa escolher group_id (400 com lista). Levanta DiaconError em
    403 (não-líder) ou 404 (sem encontro com check-in).
    """
    if not _enabled():
        raise DiaconError("Diacon não configurado")
    url = f"{_base_url()}/cells/summary"
    params: dict[str, Any] = {"phone": phone}
    if group_id:
        params["group_id"] = group_id
    if date:
        params["date"] = date
    async with httpx.AsyncClient(timeout=settings.diacon_timeout_seconds) as client:
        resp = await client.get(url, headers=_headers(), params=params)
        if resp.status_code == 400 and "application/json" in resp.headers.get("content-type", ""):
            try:
                body = resp.json()
            except Exception:
                _raise_for_status(resp, endpoint="GET cells/summary")
            if "cells" in body:
                return b"", body
            _raise_for_status(resp, endpoint="GET cells/summary")
        if not resp.is_success:
            _raise_for_status(resp, endpoint="GET cells/summary")
        return resp.content, None


# ── Events ──

async def events_upcoming(limit: int = 5) -> dict[str, Any]:
    """GET /events/upcoming?limit="""
    return await _request_json("GET", "events/upcoming", params={"limit": limit})


# ── Check-in ──

async def checkin(
    *,
    qr_token: str,
    phone: str,
    name: str | None = None,
    lat: float | None = None,
    lng: float | None = None,
) -> dict[str, Any]:
    """POST /checkin"""
    body: dict[str, Any] = {"qr_token": qr_token, "phone": phone}
    if name:
        body["name"] = name
    if lat is not None and lng is not None:
        body["lat"] = lat
        body["lng"] = lng
    return await _request_json("POST", "checkin", json_body=body)


# ── Oração ──

async def oracao_link(phone: str) -> dict[str, Any]:
    """POST /oracao/link — link autenticado + card do dia."""
    return await _request_json("POST", "oracao/link", json_body={"phone": phone})


async def oracao_pedido(
    *,
    request: str,
    phone: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """POST /oracao/pedido — registra pedido na fila pastoral."""
    body: dict[str, Any] = {"request": request}
    if phone:
        body["phone"] = phone
    if name:
        body["name"] = name
    return await _request_json("POST", "oracao/pedido", json_body=body)


async def oracao_today() -> dict[str, Any]:
    """GET /oracao/today — motivo de oração do dia."""
    return await _request_json("GET", "oracao/today")


# ── Aniversariantes ──

async def birthdays(range_: str = "week") -> dict[str, Any]:
    """GET /birthdays?range=today|week|month"""
    return await _request_json("GET", "birthdays", params={"range": range_})


# ── Pastoral ──

async def pastoral_create(
    *,
    area: str,
    title: str,
    context: str | None = None,
    priority: str = "normal",
    phone: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """POST /pastoral — cria tarefa de acompanhamento.

    area ∈ {ministry_interest, cell_interest, decision, pastoral_care,
            visit, follow_up, baptism, discipleship, other}
    priority ∈ {low, normal, high, critical}
    """
    body: dict[str, Any] = {"area": area, "title": title, "priority": priority}
    if context:
        body["context"] = context
    if phone:
        body["phone"] = phone
    if name:
        body["name"] = name
    return await _request_json("POST", "pastoral", json_body=body)


# ── Admin ──

async def admin_overview(phone: str) -> dict[str, Any]:
    """GET /admin/overview?phone=... — KPIs (só pra admin)."""
    return await _request_json("GET", "admin/overview", params={"phone": phone})
