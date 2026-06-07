"""Testes para o parser de webhook da uazapi v2."""
import pytest

from app.schemas.webhook import (
    ChatInfo,
    IncomingMessage,
    KeyInfo,
    MessageInfo,
    UAZWebhookPayload,
    parse_webhook,
)


def _make_payload(**overrides) -> UAZWebhookPayload:
    """Constrói payload base de texto para testes."""
    defaults = {
        "EventType": "messages",
        "token": "test-token",
        "notification": None,
        "chat": ChatInfo(wa_chatid="5581999999999@s.whatsapp.net", wa_name="João", wa_isGroup=False),
        "message": MessageInfo(text="Olá", messageType="conversation", messageid="MSG001"),
        "key": KeyInfo(fromMe=False, remoteJid="5581999999999@s.whatsapp.net", id="MSG001"),
    }
    defaults.update(overrides)
    return UAZWebhookPayload(**defaults)


class TestParseWebhook:
    def test_text_message(self):
        payload = _make_payload()
        msg = parse_webhook(payload)

        assert msg is not None
        assert msg.phone == "5581999999999"
        assert msg.name == "João"
        assert msg.text == "Olá"
        assert msg.media_type is None
        assert msg.from_me is False
        assert msg.is_group is False
        assert msg.is_revoke is False
        assert msg.message_id == "MSG001"

    def test_image_message(self):
        payload = _make_payload(
            message=MessageInfo(
                text=None,
                messageType="imageMessage",
                messageid="MSG002",
                content=dict(
                    URL="https://example.com/image.jpg",
                    mediaKey="abc123",
                    mimetype="image/jpeg",
                    caption="Olha essa foto",
                ),
            ),
        )
        msg = parse_webhook(payload)

        assert msg is not None
        assert msg.media_type == "image"
        assert msg.media_url == "https://example.com/image.jpg"
        assert msg.text == "Olha essa foto"  # caption sobrepõe text
        assert msg.mimetype == "image/jpeg"

    def test_audio_message(self):
        payload = _make_payload(
            message=MessageInfo(
                text=None,
                messageType="audioMessage",
                messageid="MSG003",
                content=dict(
                    URL="https://example.com/audio.ogg",
                    mediaKey="def456",
                    mimetype="audio/ogg; codecs=opus",
                ),
            ),
        )
        msg = parse_webhook(payload)

        assert msg is not None
        assert msg.media_type == "audio"
        assert msg.media_url == "https://example.com/audio.ogg"

    def test_document_message(self):
        payload = _make_payload(
            message=MessageInfo(
                text=None,
                messageType="documentMessage",
                messageid="MSG004",
                content=dict(
                    URL="https://example.com/doc.pdf",
                    mimetype="application/pdf",
                    fileName="relatorio.pdf",
                ),
            ),
        )
        msg = parse_webhook(payload)

        assert msg is not None
        assert msg.media_type == "document"
        assert msg.mimetype == "application/pdf"

    def test_video_message(self):
        payload = _make_payload(
            message=MessageInfo(
                text=None,
                messageType="videoMessage",
                messageid="MSG005",
                content=dict(
                    URL="https://example.com/video.mp4",
                    mimetype="video/mp4",
                ),
            ),
        )
        msg = parse_webhook(payload)

        assert msg is not None
        assert msg.media_type == "video"

    def test_sticker_message(self):
        payload = _make_payload(
            message=MessageInfo(
                text=None,
                messageType="stickerMessage",
                messageid="MSG006",
                content=dict(URL="https://example.com/sticker.webp"),
            ),
        )
        msg = parse_webhook(payload)

        assert msg is not None
        assert msg.media_type == "sticker"

    def test_from_me(self):
        payload = _make_payload(
            key=KeyInfo(fromMe=True, remoteJid="5581999999999@s.whatsapp.net", id="MSG007"),
        )
        msg = parse_webhook(payload)

        assert msg is not None
        assert msg.from_me is True

    def test_group_message(self):
        payload = _make_payload(
            chat=ChatInfo(wa_chatid="group@g.us", wa_name="Grupo", wa_isGroup=True),
        )
        msg = parse_webhook(payload)

        assert msg is not None
        assert msg.is_group is True

    def test_revoke(self):
        payload = _make_payload(notification="REVOKE")
        msg = parse_webhook(payload)

        assert msg is not None
        assert msg.is_revoke is True

    def test_no_key_still_extracts_phone_from_chat(self):
        # uazapi v2: telefone vem de chat.wa_chatid mesmo sem key
        payload = _make_payload(key=None)
        msg = parse_webhook(payload)
        assert msg is not None
        assert msg.phone == "5581999999999"

    def test_no_phone_anywhere_returns_none(self):
        # Sem chat, sem message.chatid, sem key.remoteJid → None
        payload = _make_payload(
            chat=None,
            message=MessageInfo(text="oi", messageType="conversation", messageid="X"),
            key=KeyInfo(fromMe=False, remoteJid=None, id="X"),
        )
        msg = parse_webhook(payload)
        assert msg is None

    def test_phone_extraction_strips_suffix(self):
        payload = _make_payload(
            chat=ChatInfo(wa_chatid="5581998765432@s.whatsapp.net", wa_name="X"),
            key=KeyInfo(fromMe=False, remoteJid="5581998765432@s.whatsapp.net", id="X"),
        )
        msg = parse_webhook(payload)

        assert msg is not None
        assert msg.phone == "5581998765432"

    def test_ptt_maps_to_audio(self):
        payload = _make_payload(
            message=MessageInfo(
                text=None,
                messageType="pttMessage",
                messageid="MSG008",
                content=dict(URL="https://example.com/ptt.ogg"),
            ),
        )
        msg = parse_webhook(payload)

        assert msg is not None
        assert msg.media_type == "audio"

    def test_document_with_caption(self):
        payload = _make_payload(
            message=MessageInfo(
                text=None,
                messageType="documentWithCaptionMessage",
                messageid="MSG009",
                content=dict(
                    URL="https://example.com/doc.pdf",
                    mimetype="application/pdf",
                    caption="Segue o documento",
                ),
            ),
        )
        msg = parse_webhook(payload)

        assert msg is not None
        assert msg.media_type == "document"
        assert msg.text == "Segue o documento"

    def test_jid_lid_suffix(self):
        """JID com sufixo @lid (usado internamente pela uazapi v2)."""
        payload = _make_payload(
            key=KeyInfo(fromMe=False, remoteJid="5581999888777@lid", id="MSG010"),
            chat=ChatInfo(wa_chatid="5581999888777@lid", wa_name="Maria"),
        )
        msg = parse_webhook(payload)

        assert msg is not None
        assert msg.phone == "5581999888777"
        assert msg.name == "Maria"

    def test_jid_without_suffix(self):
        """JID que é apenas o número sem @ (em chat.wa_chatid)."""
        payload = _make_payload(
            chat=ChatInfo(wa_chatid="5581999888777", wa_name="X"),
            key=KeyInfo(fromMe=False, remoteJid="5581999888777", id="MSG011"),
        )
        msg = parse_webhook(payload)

        assert msg is not None
        assert msg.phone == "5581999888777"
