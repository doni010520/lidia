"""Testes Fase 5 — media_processor (com decrypt via uazapi), drive_client, tools de mídia."""
from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Helper: fake PDF bytes ──
def _make_pdf_b64(text: str = "Relatório de teste") -> str:
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 72), text)
    pdf_bytes = doc.tobytes()
    doc.close()
    return base64.b64encode(pdf_bytes).decode()


# ── _download_media_bytes ──

class TestDownloadMediaBytes:
    @pytest.mark.asyncio
    async def test_download_returns_bytes(self):
        from app.services.media_processor import _download_media_bytes
        raw = base64.b64encode(b"fake content").decode()
        mock_uaz = MagicMock()
        mock_uaz.download_message = AsyncMock(return_value={"file": raw})
        with patch("app.services.media_processor.get_uaz_client", return_value=mock_uaz):
            result = await _download_media_bytes("MSG001")
        assert result == b"fake content"

    @pytest.mark.asyncio
    async def test_download_no_file_field(self):
        from app.services.media_processor import _download_media_bytes
        mock_uaz = MagicMock()
        mock_uaz.download_message = AsyncMock(return_value={"status": "ok"})
        with patch("app.services.media_processor.get_uaz_client", return_value=mock_uaz):
            result = await _download_media_bytes("MSG002")
        assert result is None

    @pytest.mark.asyncio
    async def test_download_exception(self):
        from app.services.media_processor import _download_media_bytes
        mock_uaz = MagicMock()
        mock_uaz.download_message = AsyncMock(side_effect=Exception("timeout"))
        with patch("app.services.media_processor.get_uaz_client", return_value=mock_uaz):
            result = await _download_media_bytes("MSG003")
        assert result is None


# ── transcribe_audio ──

class TestTranscribeAudio:
    @pytest.mark.asyncio
    async def test_success(self):
        from app.services.media_processor import transcribe_audio
        mock_uaz = MagicMock()
        mock_uaz.download_message = AsyncMock(return_value={"transcription": "Olá, tudo bem?"})
        with patch("app.services.media_processor.get_uaz_client", return_value=mock_uaz):
            result = await transcribe_audio("MSG001")
        assert result == "Olá, tudo bem?"

    @pytest.mark.asyncio
    async def test_error(self):
        from app.services.media_processor import transcribe_audio
        mock_uaz = MagicMock()
        mock_uaz.download_message = AsyncMock(side_effect=Exception("err"))
        with patch("app.services.media_processor.get_uaz_client", return_value=mock_uaz):
            result = await transcribe_audio("MSG002")
        assert result == ""


# ── describe_image ──

class TestDescribeImage:
    @pytest.mark.asyncio
    async def test_success_uses_base64_data_url(self):
        from app.services.media_processor import describe_image
        img_bytes = b"\x89PNG\r\n\x1a\nfake"
        img_b64 = base64.b64encode(img_bytes).decode()

        mock_uaz = MagicMock()
        mock_uaz.download_message = AsyncMock(return_value={"file": img_b64})

        mock_choice = MagicMock()
        mock_choice.message.content = "Uma foto de igreja"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with (
            patch("app.services.media_processor.get_uaz_client", return_value=mock_uaz),
            patch("app.services.media_processor.openai.AsyncOpenAI", return_value=mock_client),
        ):
            result = await describe_image("MSG001", "image/png")

        assert "igreja" in result
        # Verificar que o data URL base64 foi usado (não URL externa)
        call_args = mock_client.chat.completions.create.call_args
        content = call_args.kwargs["messages"][0]["content"]
        image_block = content[1]
        assert image_block["image_url"]["url"].startswith("data:image/png;base64,")

    @pytest.mark.asyncio
    async def test_download_fails(self):
        from app.services.media_processor import describe_image
        mock_uaz = MagicMock()
        mock_uaz.download_message = AsyncMock(return_value={"status": "ok"})
        with patch("app.services.media_processor.get_uaz_client", return_value=mock_uaz):
            result = await describe_image("MSG002")
        assert "não foi possível" in result


# ── extract_document ──

class TestExtractDocument:
    @pytest.mark.asyncio
    async def test_extract_pdf_via_uaz_download(self):
        from app.services.media_processor import extract_document
        pdf_b64 = _make_pdf_b64("Relatório de teste da PAES")
        mock_uaz = MagicMock()
        mock_uaz.download_message = AsyncMock(return_value={"file": pdf_b64})
        with patch("app.services.media_processor.get_uaz_client", return_value=mock_uaz):
            result = await extract_document("MSG001", "application/pdf")
        assert "PDF" in result
        assert "Relatório" in result

    @pytest.mark.asyncio
    async def test_download_fails(self):
        from app.services.media_processor import extract_document
        mock_uaz = MagicMock()
        mock_uaz.download_message = AsyncMock(side_effect=Exception("err"))
        with patch("app.services.media_processor.get_uaz_client", return_value=mock_uaz):
            result = await extract_document("MSG002", "application/pdf")
        assert "não foi possível" in result

    @pytest.mark.asyncio
    async def test_unsupported_mime(self):
        from app.services.media_processor import extract_document
        raw_b64 = base64.b64encode(b"binary").decode()
        mock_uaz = MagicMock()
        mock_uaz.download_message = AsyncMock(return_value={"file": raw_b64})
        with patch("app.services.media_processor.get_uaz_client", return_value=mock_uaz):
            result = await extract_document("MSG003", "application/octet-stream")
        assert "não suportado" in result


# ── handle_video ──

class TestHandleVideo:
    @pytest.mark.asyncio
    async def test_success(self):
        from app.services.media_processor import handle_video
        vid_b64 = base64.b64encode(b"fake video").decode()
        mock_uaz = MagicMock()
        mock_uaz.download_message = AsyncMock(return_value={"file": vid_b64})
        with (
            patch("app.services.media_processor.get_uaz_client", return_value=mock_uaz),
            patch("app.services.drive_client.upload_bytes", return_value="DRIVE_123"),
        ):
            result = await handle_video("MSG001")
        assert result == "DRIVE_123"

    @pytest.mark.asyncio
    async def test_download_fails(self):
        from app.services.media_processor import handle_video
        mock_uaz = MagicMock()
        mock_uaz.download_message = AsyncMock(return_value={"status": "ok"})
        with patch("app.services.media_processor.get_uaz_client", return_value=mock_uaz):
            result = await handle_video("MSG002")
        assert result == ""


# ── drive_client ──

class TestDriveClient:
    def test_get_public_url(self):
        from app.services.drive_client import get_public_url
        assert "ABC123" in get_public_url("ABC123")

    def test_detect_uaz_type(self):
        from app.services.drive_client import detect_uaz_type
        assert detect_uaz_type("image/jpeg") == "image"
        assert detect_uaz_type("video/mp4") == "video"
        assert detect_uaz_type("application/pdf") == "document"
        assert detect_uaz_type("unknown/type") == "document"


# ── Tools de mídia ──

class TestPaesListarArquivos:
    @pytest.mark.asyncio
    async def test_lista_arquivos(self):
        from app.tools.tool_modules.paes_listar_arquivos import execute
        with patch("app.tools.tool_modules.paes_listar_arquivos.drive_client") as mock:
            mock.search.return_value = [
                {"name": "flyer.jpg", "mimeType": "image/jpeg"},
                {"name": "video.mp4", "mimeType": "video/mp4"},
            ]
            result = await execute({"nome": "teste"}, "5581999", AsyncMock())
        assert "2 arquivo" in result

    @pytest.mark.asyncio
    async def test_nome_obrigatorio(self):
        from app.tools.tool_modules.paes_listar_arquivos import execute
        result = await execute({}, "5581999", AsyncMock())
        assert "obrigatório" in result


class TestPaesDownloadArquivos:
    @pytest.mark.asyncio
    async def test_envia_arquivo(self):
        from app.tools.tool_modules.paes_download_arquivos import execute
        mock_uaz = MagicMock()
        mock_uaz.send_media = AsyncMock(return_value={"status": "ok"})
        with (
            patch("app.tools.tool_modules.paes_download_arquivos.drive_client") as mock_drive,
            patch("app.tools.tool_modules.paes_download_arquivos.get_uaz_client", return_value=mock_uaz),
        ):
            mock_drive.search.return_value = [{"id": "F1", "name": "flyer.jpg", "mimeType": "image/jpeg"}]
            mock_drive.get_public_url.return_value = "https://drive/F1"
            mock_drive.detect_uaz_type.return_value = "image"
            result = await execute({"arquivos": ["flyer.jpg"], "telefone": "5581999"}, "5581999", AsyncMock())
        assert "sucesso" in result.lower()


class TestEncaminharVideoLouvor:
    @pytest.mark.asyncio
    async def test_encaminha(self):
        from app.tools.tool_modules.encaminhar_video_louvor import execute
        from app.models.equipes import EquipeResponsavel
        equipe = EquipeResponsavel(id=1, equipe="Louvor", telefones_responsaveis=["5581998390927"])
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = equipe
        mock_db.execute.return_value = mock_result
        mock_uaz = MagicMock()
        mock_uaz.send_text = AsyncMock(return_value={"status": "ok"})
        with (
            patch("app.tools.tool_modules.encaminhar_video_louvor.get_uaz_client", return_value=mock_uaz),
            patch("app.tools.tool_modules.encaminhar_video_louvor.drive_client"),
        ):
            result = await execute({"drive_file_id": "X", "nome": "João", "telefone": "55"}, "55", mock_db)
        assert "1 responsável" in result

    @pytest.mark.asyncio
    async def test_drive_file_id_obrigatorio(self):
        from app.tools.tool_modules.encaminhar_video_louvor import execute
        result = await execute({}, "5581999", AsyncMock())
        assert "obrigatório" in result
