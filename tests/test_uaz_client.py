"""Testes para o UAZClient — mock httpx com respx."""
import pytest
import respx
from httpx import Response

from app.services.uaz_client import UAZClient


@pytest.fixture
def uaz(monkeypatch):
    monkeypatch.setenv("UAZ_BASE_URL", "https://test.uazapi.com")
    monkeypatch.setenv("UAZ_TOKEN", "test-token-123")
    monkeypatch.setenv("DRY_RUN", "false")
    # Reload settings
    from app.core.config import Settings
    s = Settings()
    monkeypatch.setattr("app.services.uaz_client.settings", s)

    client = UAZClient()
    client.base_url = "https://test.uazapi.com"
    client.token = "test-token-123"
    return client


class TestUAZClientHeaders:
    @respx.mock
    @pytest.mark.asyncio
    async def test_send_text_uses_token_header(self, uaz):
        route = respx.post("https://test.uazapi.com/send/text").mock(
            return_value=Response(200, json={"status": "ok"})
        )

        await uaz.send_text("5581999999999", "Hello")

        assert route.called
        req = route.calls[0].request
        assert req.headers["token"] == "test-token-123"
        assert req.headers["content-type"] == "application/json"

    @respx.mock
    @pytest.mark.asyncio
    async def test_send_text_payload(self, uaz):
        route = respx.post("https://test.uazapi.com/send/text").mock(
            return_value=Response(200, json={"status": "ok"})
        )

        await uaz.send_text("5581999999999", "Olá mundo", link_preview=True)

        import json
        body = json.loads(route.calls[0].request.content)
        assert body["number"] == "5581999999999"
        assert body["text"] == "Olá mundo"
        assert body["linkPreview"] is True

    @respx.mock
    @pytest.mark.asyncio
    async def test_send_media_image(self, uaz):
        route = respx.post("https://test.uazapi.com/send/media").mock(
            return_value=Response(200, json={"status": "ok"})
        )

        await uaz.send_media(
            "5581999999999",
            "https://example.com/img.jpg",
            "image",
            text="Legenda",
        )

        import json
        body = json.loads(route.calls[0].request.content)
        assert body["number"] == "5581999999999"
        assert body["file"] == "https://example.com/img.jpg"
        assert body["type"] == "image"
        assert body["text"] == "Legenda"

    @respx.mock
    @pytest.mark.asyncio
    async def test_send_presence(self, uaz):
        route = respx.post("https://test.uazapi.com/message/presence").mock(
            return_value=Response(200, json={"status": "ok"})
        )

        await uaz.send_presence("5581999999999", "composing", delay=3000)

        import json
        body = json.loads(route.calls[0].request.content)
        assert body["presence"] == "composing"
        assert body["delay"] == 3000

    @respx.mock
    @pytest.mark.asyncio
    async def test_download_message_with_transcribe(self, uaz):
        route = respx.post("https://test.uazapi.com/message/download").mock(
            return_value=Response(200, json={"transcription": "Olá mundo"})
        )

        result = await uaz.download_message("MSG001", transcribe=True, openai_apikey="sk-test")

        import json
        body = json.loads(route.calls[0].request.content)
        assert body["transcribe"] is True
        assert body["openai_apikey"] == "sk-test"
        assert result["transcription"] == "Olá mundo"

    @respx.mock
    @pytest.mark.asyncio
    async def test_update_chatbot_settings(self, uaz):
        route = respx.post("https://test.uazapi.com/instance/updatechatbotsettings").mock(
            return_value=Response(200, json={"status": "ok"})
        )

        await uaz.update_chatbot_settings(
            chatbot_enabled=True,
            chatbot_stop_when_you_send_msg=30,
        )

        import json
        body = json.loads(route.calls[0].request.content)
        assert body["chatbot_enabled"] is True
        assert body["chatbot_stopWhenYouSendMsg"] == 30

    @respx.mock
    @pytest.mark.asyncio
    async def test_react(self, uaz):
        route = respx.post("https://test.uazapi.com/message/react").mock(
            return_value=Response(200, json={"status": "ok"})
        )

        await uaz.react("5581999999999", "👍", "MSG001")

        import json
        body = json.loads(route.calls[0].request.content)
        assert body["text"] == "👍"
        assert body["id"] == "MSG001"

    @respx.mock
    @pytest.mark.asyncio
    async def test_download_uses_id_field(self, uaz):
        """Valida que download_message envia campo 'id' (não 'messageId')."""
        route = respx.post("https://test.uazapi.com/message/download").mock(
            return_value=Response(200, json={"data": "ok"})
        )
        await uaz.download_message("ABC123")

        import json
        body = json.loads(route.calls[0].request.content)
        assert "id" in body
        assert body["id"] == "ABC123"
        assert "messageId" not in body

    @respx.mock
    @pytest.mark.asyncio
    async def test_mark_read_uses_id_array(self, uaz):
        """Valida que mark_read envia campo 'id' (array), não 'messageIds'."""
        route = respx.post("https://test.uazapi.com/message/markread").mock(
            return_value=Response(200, json={"status": "ok"})
        )
        await uaz.mark_read(["MSG1", "MSG2"])

        import json
        body = json.loads(route.calls[0].request.content)
        assert "id" in body
        assert body["id"] == ["MSG1", "MSG2"]
        assert "messageIds" not in body

    @respx.mock
    @pytest.mark.asyncio
    async def test_find_messages_uses_id_field(self, uaz):
        """Valida que find_messages envia campo 'id' (não 'messageId')."""
        route = respx.post("https://test.uazapi.com/message/find").mock(
            return_value=Response(200, json={"messages": []})
        )
        await uaz.find_messages(message_id="XYZ")

        import json
        body = json.loads(route.calls[0].request.content)
        assert "id" in body
        assert body["id"] == "XYZ"
        assert "messageId" not in body

    @respx.mock
    @pytest.mark.asyncio
    async def test_send_text_uses_replyid_lowercase(self, uaz):
        """Valida que send_text envia campo 'replyid' (não 'replyId')."""
        route = respx.post("https://test.uazapi.com/send/text").mock(
            return_value=Response(200, json={"status": "ok"})
        )
        await uaz.send_text("5581999999999", "teste", reply_id="REPLY001")

        import json
        body = json.loads(route.calls[0].request.content)
        assert "replyid" in body
        assert body["replyid"] == "REPLY001"
        assert "replyId" not in body

    @respx.mock
    @pytest.mark.asyncio
    async def test_send_media_uses_replyid_lowercase(self, uaz):
        """Valida que send_media envia campo 'replyid' (não 'replyId')."""
        route = respx.post("https://test.uazapi.com/send/media").mock(
            return_value=Response(200, json={"status": "ok"})
        )
        await uaz.send_media("5581999999999", "https://img.jpg", "image", reply_id="REPLY002")

        import json
        body = json.loads(route.calls[0].request.content)
        assert "replyid" in body
        assert body["replyid"] == "REPLY002"
        assert "replyId" not in body

    @respx.mock
    @pytest.mark.asyncio
    async def test_edit_lead(self, uaz):
        route = respx.post("https://test.uazapi.com/chat/editLead").mock(
            return_value=Response(200, json={"status": "ok"})
        )

        await uaz.edit_lead("5581999999999@s.whatsapp.net", lead_name="João Silva")

        import json
        body = json.loads(route.calls[0].request.content)
        assert body["id"] == "5581999999999@s.whatsapp.net"
        assert body["lead_name"] == "João Silva"


class TestDryRun:
    @pytest.mark.asyncio
    async def test_dry_run_does_not_send(self, uaz, monkeypatch):
        from app.core.config import Settings
        s = Settings()
        s.dry_run = True
        monkeypatch.setattr("app.services.uaz_client.settings", s)

        result = await uaz.send_text("5581999999999", "Teste dry run")
        assert result == {"dry_run": True}
