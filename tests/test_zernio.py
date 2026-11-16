"""Canal Zernio (coexistência): webhook → IncomingMessage e envio."""
from __future__ import annotations

import hashlib
import hmac
from unittest.mock import AsyncMock

import pytest

from app.api import webhook_zernio as wz
from app.services import zernio_client as zc


def _ev(event="message.received", **m):
    base = {"id": "m1", "text": "oi", "direction": "incoming"}
    base.update(m)
    return {"id": "e1", "event": event, "message": base,
            "conversation": {"id": "c1", "participantId": "+55 81 99788-4531", "participantName": "Tarcisio"}}


def test_texto_recebido():
    tipo, msg = wz.parse_evento(_ev())
    assert tipo == "entrada"
    assert (msg.phone, msg.text, msg.name, msg.from_me) == ("5581997884531", "oi", "Tarcisio", False)


def test_audio_recebido_traz_url():
    tipo, msg = wz.parse_evento(_ev(text=None, attachments=[{"type": "audio", "url": "https://x/a.ogg", "mimeType": "audio/ogg"}]))
    assert msg.media_type == "audio" and msg.media_url == "https://x/a.ogg"


def test_clique_em_botao():
    _, msg = wz.parse_evento(_ev(text="Quero ver 🎁", metadata={"interactiveType": "button_reply", "interactiveId": "devocional_ver"}))
    assert msg.button_id == "devocional_ver"


def test_eco_da_api_e_ignorado_e_celular_e_humano():
    assert wz.parse_evento(_ev("message.sent", sentVia="api"))[0] == "ignorar"
    assert wz.parse_evento(_ev("message.sent", source="cloud_api"))[0] == "ignorar"
    tipo, msg = wz.parse_evento(_ev("message.sent", source="whatsapp_business_app", text="Roberta aqui!"))
    assert tipo == "humano" and msg.from_me


def test_assinatura(monkeypatch):
    monkeypatch.setattr(wz.settings, "zernio_webhook_secret", "s3")
    raw = b'{"a":1}'
    sig = hmac.new(b"s3", raw, hashlib.sha256).hexdigest()
    assert wz._assinatura_ok(raw, sig)
    assert not wz._assinatura_ok(raw, "x")
    assert not wz._assinatura_ok(raw, None)


@pytest.mark.asyncio
async def test_envio_de_texto_e_botoes(monkeypatch):
    monkeypatch.setattr(zc.settings, "zernio_account_id", "acc1")
    cli = zc.ZernioClient()
    post = AsyncMock(return_value={"data": {"messageId": "z9", "conversationId": "c1"}})
    monkeypatch.setattr(cli, "_post_conversa", post)

    r = await cli.send_text("558197884531@s.whatsapp.net", "olá")
    payload, idem = post.await_args.args
    assert payload == {"accountId": "acc1", "participantId": "558197884531", "message": "olá", "linkPreview": False}
    assert idem and r["messageid"] == "z9"

    await cli.send_buttons("5581", "Quer ver?", [("Quero ver 🎁", "a"), ("Não quero receber", "b")])
    payload, _ = post.await_args.args
    assert payload["buttons"] == [{"type": "postback", "title": "Quero ver 🎁", "payload": "a"},
                                  {"type": "postback", "title": "Não quero receber", "payload": "b"}]


@pytest.mark.asyncio
async def test_pdf_vira_link_temporario(monkeypatch):
    monkeypatch.setattr(zc.settings, "zernio_account_id", "acc1")
    cli = zc.ZernioClient()
    post = AsyncMock(return_value={"data": {"messageId": "z1"}})
    monkeypatch.setattr(cli, "_post_conversa", post)
    from app.services import media_temp
    monkeypatch.setattr(media_temp, "publicar", AsyncMock(return_value="https://lidia.benitechlab.com/m/t/qr.pdf"))
    await cli.send_media_bytes("5581", b"%PDF", "application/pdf", "document", text="QR", doc_name="qr.pdf")
    payload, _ = post.await_args.args
    assert payload["attachmentUrl"].endswith("/qr.pdf")
    assert payload["attachmentType"] == "file" and payload["attachmentName"] == "qr.pdf" and payload["message"] == "QR"


@pytest.mark.asyncio
async def test_descobre_a_conta_pelo_perfil(monkeypatch):
    monkeypatch.setattr(zc.settings, "zernio_account_id", "")
    monkeypatch.setattr(zc.settings, "zernio_profile_id", "perfilPAES")
    cli = zc.ZernioClient()
    req = AsyncMock(return_value={"accounts": [
        {"_id": "ig1", "platform": "instagram", "isActive": True},
        {"_id": "wa1", "platform": "whatsapp", "isActive": True, "username": "+5581"},
    ]})
    monkeypatch.setattr(cli, "_req", req)
    assert await cli._conta() == "wa1"
    assert req.await_args.kwargs["params"] == {"profileId": "perfilPAES"}
    assert await cli._conta() == "wa1" and req.await_count == 1  # guardado


@pytest.mark.asyncio
async def test_sem_conta_conectada_falha_e_espera_1_min(monkeypatch):
    monkeypatch.setattr(zc.settings, "zernio_account_id", "")
    cli = zc.ZernioClient()
    req = AsyncMock(return_value={"accounts": []})
    monkeypatch.setattr(cli, "_req", req)
    for _ in range(2):
        with pytest.raises(zc.ZernioError):
            await cli._conta()
    assert req.await_count == 1
