from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")
    wa_chatid: str | None = None
    wa_name: str | None = None
    wa_isGroup: bool = False
    wa_unreadCount: int | None = None
    name: str | None = None
    phone: str | None = None
    image: str | None = None


class MessageInfo(BaseModel):
    """Schema flexível pra aceitar v1 e v2 do uazapi (campos opcionais)."""
    model_config = ConfigDict(extra="ignore")

    # Identificação
    id: str | None = None
    messageid: str | None = None
    chatid: str | None = None
    sender: str | None = None

    # Texto / tipo
    text: str | None = None
    messageType: str | None = None
    type: str | None = None
    mediaType: str | None = None

    # Flags
    fromMe: bool = False
    isGroup: bool = False
    wasSentByApi: bool = False

    # Conteúdo (na v2 pode vir string OU objeto)
    content: Any | None = None
    caption: str | None = None
    URL: str | None = None
    mediaKey: str | None = None
    mimetype: str | None = None
    fileName: str | None = None


class KeyInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")
    fromMe: bool = False
    remoteJid: str | None = None
    id: str | None = None


class UAZWebhookPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    EventType: str | None = None
    token: str | None = None
    notification: str | None = None
    owner: str | None = None
    instanceName: str | None = None
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
    latitude: float | None = None
    longitude: float | None = None


_MEDIA_MAP: dict[str, str] = {
    # versão v1 (camelCase com 'Message' suffix)
    "imageMessage": "image",
    "audioMessage": "audio",
    "documentMessage": "document",
    "videoMessage": "video",
    "stickerMessage": "sticker",
    "documentWithCaptionMessage": "document",
    "pttMessage": "audio",
    # versão v2 (PascalCase ou snake)
    "Image": "image",
    "Audio": "audio",
    "Video": "video",
    "Document": "document",
    "Sticker": "sticker",
    "Ptt": "audio",
}

# Tipos de mensagem de localização (v1 e v2)
_LOCATION_TYPES = {"locationMessage", "Location", "liveLocationMessage", "LiveLocation"}


def parse_webhook(payload: UAZWebhookPayload) -> IncomingMessage | None:
    """Converte payload uazapi (v1 ou v2) em IncomingMessage normalizado.

    Retorna None se faltar dados essenciais (telefone).
    """
    msg = payload.message
    chat = payload.chat
    key = payload.key

    # phone: prioriza chat.wa_chatid, depois message.chatid, depois key.remoteJid
    phone = ""
    if chat and chat.wa_chatid:
        phone = _extract_phone(chat.wa_chatid)
    if not phone and msg and msg.chatid:
        phone = _extract_phone(msg.chatid)
    if not phone and key and key.remoteJid:
        phone = _extract_phone(key.remoteJid)

    if not phone:
        return None

    # text + mídia + localização
    text: str | None = None
    media_url: str | None = None
    media_type: str | None = None
    media_key: str | None = None
    mimetype: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    if msg:
        text = msg.text
        msg_type = msg.messageType or msg.type or msg.mediaType or ""

        # content pode ser:
        #   - string  (v2 texto): "Oi Lidia"
        #   - dict    (v1 mídia): {"URL":"...","mediaKey":"...","mimetype":"..."}
        #   - dict    (localização): {"degreesLatitude":..., "degreesLongitude":...}
        c = msg.content

        # ── Localização ──
        if msg_type in _LOCATION_TYPES:
            if isinstance(c, dict):
                latitude = c.get("degreesLatitude") or c.get("latitude")
                longitude = c.get("degreesLongitude") or c.get("longitude")
                try:
                    latitude = float(latitude) if latitude is not None else None
                    longitude = float(longitude) if longitude is not None else None
                except (TypeError, ValueError):
                    latitude, longitude = None, None
        elif isinstance(c, dict):
            media_url = c.get("URL") or c.get("url")
            media_key = c.get("mediaKey")
            mimetype = c.get("mimetype")
            cap = c.get("caption")
            if cap:
                text = cap
        elif isinstance(c, str) and not text:
            text = c

        # Campos diretos da v2 que podem ter mídia
        if not media_url and msg.URL:
            media_url = msg.URL
        if not media_key and msg.mediaKey:
            media_key = msg.mediaKey
        if not mimetype and msg.mimetype:
            mimetype = msg.mimetype
        if not text and msg.caption:
            text = msg.caption

        media_type = _MEDIA_MAP.get(msg_type) or (
            "image" if "image" in msg_type.lower() else
            "audio" if "audio" in msg_type.lower() or "ptt" in msg_type.lower() else
            "video" if "video" in msg_type.lower() else
            "document" if "document" in msg_type.lower() else
            None
        )

    # message_id
    message_id = None
    if msg:
        message_id = msg.messageid or msg.id
    if not message_id and key:
        message_id = key.id

    # from_me / is_group
    from_me = (msg.fromMe if msg else False) or (key.fromMe if key else False)
    is_group = (msg.isGroup if msg else False) or (chat.wa_isGroup if chat else False)

    # name
    name = None
    if chat:
        name = chat.wa_name or chat.name

    return IncomingMessage(
        phone=phone,
        name=name,
        text=text,
        media_url=media_url,
        media_type=media_type,
        media_key=media_key,
        mimetype=mimetype,
        message_id=message_id,
        is_group=is_group,
        from_me=from_me,
        is_revoke=payload.notification == "REVOKE",
        latitude=latitude,
        longitude=longitude,
    )
