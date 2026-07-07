from __future__ import annotations

import hashlib
import hmac

from fastapi import APIRouter, Depends, Request, Response
from loguru import logger
from pydantic import ValidationError

from app.core.config import settings
from app.schemas.webhook import IncomingMessage, UAZWebhookPayload, parse_webhook

router = APIRouter()


def _verify_hmac(body: bytes, signature: str) -> bool:
    """Valida HMAC SHA256 se UAZ_WEBHOOK_SECRET estiver configurado."""
    expected = hmac.new(
        settings.uaz_webhook_secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/hooks/sheets-sync")
async def sheets_sync_hook(request: Request) -> Response:
    """Gatilho chamado pelo Apps Script (onEdit) da planilha → sincroniza na hora.
    Autenticado por ?key= (settings.sheets_hook_key). Roda em background."""
    import asyncio

    key = request.query_params.get("key", "")
    if not settings.sheets_hook_key or key != settings.sheets_hook_key:
        return Response(status_code=401)

    from app.workers.sheets_sync import run_all_syncs
    asyncio.create_task(run_all_syncs())
    logger.info("sheets-sync-hook disparado pela planilha")
    return Response(status_code=202)


@router.post("/webhook")
async def webhook_handler(request: Request) -> Response:
    """Endpoint principal que recebe webhooks da uazapi v2."""
    body = await request.body()

    # ── 1. HMAC (opcional) ──
    if settings.uaz_webhook_secret:
        sig = request.headers.get("x-signature", "")
        if not _verify_hmac(body, sig):
            logger.warning("Webhook rejeitado: HMAC inválido")
            return Response(status_code=401)

    # ── 2. Parse payload ──
    try:
        raw = await request.json()
        # uazapi pode enviar com envelope {body: {...}} ou payload direto
        if isinstance(raw, dict) and "body" in raw and "EventType" not in raw:
            raw = raw["body"]
        payload = UAZWebhookPayload.model_validate(raw)
    except (ValidationError, Exception) as exc:
        logger.warning(f"Webhook payload inválido: {exc}")
        return Response(status_code=200)  # 200 para não gerar retry na uazapi

    # ── 3. Validar token ──
    if settings.uaz_token and payload.token != settings.uaz_token:
        logger.warning(f"Webhook rejeitado: token mismatch ({payload.token})")
        return Response(status_code=200)

    # ── 4. Filtrar EventType ──
    if payload.EventType != "messages":
        logger.debug(f"Evento ignorado: {payload.EventType}")
        return Response(status_code=200)

    # ── 5. Parse para IncomingMessage ──
    msg = parse_webhook(payload)
    if msg is None:
        logger.debug("Payload sem dados suficientes, ignorando")
        return Response(status_code=200)

    phone_log = logger.bind(phone=msg.phone, message_id=msg.message_id)

    # ── 6. Filtros ──
    if msg.is_group:
        phone_log.debug("Mensagem de grupo ignorada")
        return Response(status_code=200)

    if msg.is_revoke:
        phone_log.debug("Revogação de mensagem ignorada")
        return Response(status_code=200)

    # ── 7. Dedup por message_id ──
    from app.services.deps import get_buffer_service
    buffer = get_buffer_service()
    if msg.message_id and await buffer.is_duplicate(msg.message_id):
        phone_log.debug("Mensagem duplicada, ignorando")
        return Response(status_code=200)

    # ── 8. Rotear from_me → handoff check ──
    if msg.from_me:
        from app.services.handoff_service import handle_outgoing
        from app.db import async_session_factory
        phone_log.debug("Mensagem from_me → handoff_service")
        async with async_session_factory() as db:
            try:
                await handle_outgoing(msg, db)
            except Exception:
                phone_log.exception("Erro no handoff_service")
        return Response(status_code=200)

    # ── 9. Push no buffer + agendar processamento ──
    phone_log.info(f"Mensagem recebida: type={msg.media_type or 'text'}")
    from app.services.deps import get_process_callback
    await buffer.push(msg, get_process_callback())

    return Response(status_code=200)
