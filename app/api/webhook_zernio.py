"""Canal Zernio (WhatsApp Business com coexistência).

- POST /webhooks/zernio: mensagens. Só processa com WHATSAPP_PROVIDER=zernio —
  durante a transição o número pode estar nos dois canais e a LidIA não pode
  responder duas vezes.
- GET  /conectar-whatsapp?k=: link FIXO de conexão. Cada acesso gera um link
  novo da Zernio (o deles expira) e redireciona.
- GET  /m/<token>/<nome>: arquivos temporários (PDFs) que a Zernio busca.
"""
from __future__ import annotations

import hashlib
import hmac

from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse
from loguru import logger

from app.core.config import settings
from app.schemas.webhook import IncomingMessage

router = APIRouter()

_MIDIA = {"image": "image", "video": "video", "audio": "audio", "voice": "audio",
          "file": "document", "document": "document", "sticker": "sticker"}


def _digitos(s: str | None) -> str:
    return "".join(ch for ch in (s or "") if ch.isdigit())


def _assinatura_ok(raw: bytes, header: str | None) -> bool:
    if not settings.zernio_webhook_secret:
        return True
    if not header:
        return False
    esperado = hmac.new(settings.zernio_webhook_secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, header.strip())


def _button_id(ev: dict, m: dict) -> str | None:
    """Clique em botão: o `payload` do botão volta como interactiveId."""
    for meta in (m.get("metadata"), ev.get("metadata")):
        if isinstance(meta, dict) and meta.get("interactiveId"):
            return str(meta["interactiveId"])
    return None


def parse_evento(ev: dict) -> tuple[str, IncomingMessage | None]:
    """Traduz o evento da Zernio para o IncomingMessage que o pipeline já usa.

    Retorna (tipo, msg): tipo = 'entrada' | 'humano' (equipe pelo celular) |
    'ignorar'.
    """
    nome_ev = ev.get("event") or ""
    m = ev.get("message") or {}
    conv = ev.get("conversation") or {}
    phone = _digitos(conv.get("participantId"))
    if not phone or not m:
        return "ignorar", None

    atts = m.get("attachments") or []
    a = atts[0] if atts else {}
    text = m.get("text") or None
    msg = IncomingMessage(
        phone=phone,
        name=conv.get("participantName"),
        text=text,
        media_url=a.get("url") or None,
        media_type=_MIDIA.get((a.get("type") or "").lower()) if a else None,
        mimetype=a.get("mimeType"),
        message_id=m.get("id"),
        button_id=_button_id(ev, m),
        from_me=nome_ev == "message.sent",
    )

    if nome_ev == "message.received":
        return "entrada", msg
    if nome_ev == "message.sent":
        # Envio da própria LidIA pela API volta como eco: não é a equipe.
        if m.get("sentVia") == "api" or (m.get("source") == "cloud_api" and not m.get("sentVia")):
            return "ignorar", None
        return "humano", msg
    return "ignorar", None


@router.post("/webhooks/zernio")
async def webhook_zernio(request: Request) -> Response:
    raw = await request.body()
    if not _assinatura_ok(raw, request.headers.get("x-zernio-signature")):
        logger.warning("Webhook Zernio rejeitado: assinatura inválida")
        return Response(status_code=401)
    if settings.whatsapp_provider != "zernio":
        return Response(status_code=200)
    try:
        ev = await request.json()
    except Exception:
        return Response(status_code=200)

    tipo, msg = parse_evento(ev)
    if tipo == "ignorar" or msg is None:
        return Response(status_code=200)

    from app.services.deps import get_buffer_service, get_process_callback, get_uaz_client
    buffer = get_buffer_service()
    ev_id = request.headers.get("x-zernio-event-id") or ev.get("id") or msg.message_id
    if ev_id and await buffer.is_duplicate(f"z:{ev_id}"):
        return Response(status_code=200)
    log = logger.bind(phone=msg.phone, message_id=msg.message_id)

    from app.db import async_session_factory

    if tipo == "humano":
        from app.services.handoff_service import handle_outgoing, pausar_ia
        await pausar_ia(msg.phone)
        async with async_session_factory() as db:
            try:
                await handle_outgoing(msg, db)
            except Exception:
                log.exception("Erro no handoff (Zernio)")
        return Response(status_code=200)

    # Clique em botão de campanha → resposta fixa, sem LLM
    from app.services import campanha_cursilho
    if campanha_cursilho.eh_clique(msg.button_id):
        async with async_session_factory() as db:
            try:
                await campanha_cursilho.responder_clique(get_uaz_client(), db, msg.phone, msg.button_id)
            except Exception:
                log.exception("Erro ao responder clique de campanha (Zernio)")
        return Response(status_code=200)

    log.info(f"Mensagem recebida (Zernio): type={msg.media_type or 'text'}")
    await buffer.push(msg, get_process_callback())
    return Response(status_code=200)


@router.get("/conectar-whatsapp")
async def conectar_whatsapp(k: str = "") -> Response:
    """Link fixo pra PAES conectar o número na Zernio (coexistência)."""
    if not settings.conectar_whatsapp_key or k != settings.conectar_whatsapp_key:
        return Response(status_code=404)
    import httpx
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(
            f"{settings.zernio_base_url.rstrip('/')}/connect/whatsapp",
            headers={"Authorization": f"Bearer {settings.zernio_api_key}"},
            params={"profileId": settings.zernio_profile_id, "welcome": "true",
                    "brandName": "PAES Catedral"},
        )
    if r.status_code >= 400 or not r.json().get("authUrl"):
        logger.error(f"Zernio connect falhou: {r.status_code} {r.text[:300]}")
        return Response("Não consegui gerar o link agora. Tente de novo em alguns minutos.",
                        status_code=502, media_type="text/plain; charset=utf-8")
    return RedirectResponse(r.json()["authUrl"], status_code=302)


@router.get("/m/{token}/{nome}")
async def midia_temporaria(token: str, nome: str) -> Response:
    from app.services import media_temp
    item = await media_temp.obter(token)
    if not item:
        return Response(status_code=404)
    content, mimetype, nome_arq = item
    return Response(content, media_type=mimetype,
                    headers={"Content-Disposition": f'inline; filename="{nome_arq}"'})
