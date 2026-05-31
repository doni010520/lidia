from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field


class ChatInfo(BaseModel):
    wa_chatid: str | None = None
    wa_name: str | None = None
    wa_isGroup: bool = False
    wa_unreadCount: int | None = None


class MessageContent(BaseModel):
    URL: str | None = None
    mediaKey: str | None = None
    mimetype: str | None = None
    fileName: str | None = None
    caption: str | None = None


class MessageInfo(BaseModel):
    text: str | None = None
    messageType: str | None = None
    messageid: str | None = None
    content: MessageContent | None = None


class KeyInfo(BaseModel):
    fromMe: bool = False
    remoteJid: str | None = None
    id: str | None = None


class UAZWebhookPayload(BaseModel):
    EventType: str | None = None
    token: str | None = None
    notification: str | None = None
    chat: ChatInfo | None = None
    message: MessageInfo | None = None
    key: KeyInfo | None = None
    created_at: int | None = None


_PHONE_RE = re.compile(r"\d+")


def _extract_phone(jid: str | None) -> str:
    """Extrai telefone limpo de '5511999999999@s.whatsapp.net'."""
    if not jid:
        return ""
    match = _PHONE_RE.match(jid)
    return match.group(0) if match else ""


class IncomingMessage(BaseModel):
    phone: str
    name: str | None = None
    text: str | None = None
    media_url: str | None = None
    media_type: Literal["image", "audio", "document", "video", "sticker"] | None = None
    media_key: str | None = None
    mimetype: str | None = None
    message_id: str | None = None
    is_group: bool = False
    from_me: bool = False
    is_revoke: bool = False


_MEDIA_MAP: dict[str, str] = {
    "imageMessage": "image",
    "audioMessage": "audio",
    "documentMessage": "document",
    "videoMessage": "video",
    "stickerMessage": "sticker",
    "documentWithCaptionMessage": "document",
    "pttMessage": "audio",
}


def parse_webhook(payload: UAZWebhookPayload) -> IncomingMessage | None:
    """Converte payload bruto da uazapi v2 em IncomingMessage normalizado.

    Retorna None se o payload não contiver dados suficientes para processar.
    """
    key = payload.key
    chat = payload.chat
    msg = payload.message

    if not key:
        return None

    phone = _extract_phone(key.remoteJid)
    if not phone:
        return None

    text: str | None = None
    media_url: str | None = None
    media_type: str | None = None
    media_key: str | None = None
    mimetype: str | None = None

    if msg:
        text = msg.text
        msg_type = msg.messageType or ""

        if msg.content:
            media_url = msg.content.URL
            media_key = msg.content.mediaKey
            mimetype = msg.content.mimetype
            # caption sobrepõe text quando é mídia com legenda
            if msg.content.caption:
                text = msg.content.caption

        media_type = _MEDIA_MAP.get(msg_type)

    return IncomingMessage(
        phone=phone,
        name=chat.wa_name if chat else None,
        text=text,
        media_url=media_url,
        media_type=media_type,
        media_key=media_key,
        mimetype=mimetype,
        message_id=msg.messageid if msg else (key.id if key else None),
        is_group=chat.wa_isGroup if chat else False,
        from_me=key.fromMe if key else False,
        is_revoke=payload.notification == "REVOKE",
    )
