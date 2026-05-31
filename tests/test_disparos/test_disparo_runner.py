"""Testes para disparo_runner — envio, cancelamento, idempotência."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest


class TestRunDisparo:
    @pytest.mark.asyncio
    async def test_toggle_chatbot_settings(self):
        """Verifica que chatbot_stop é desativado antes e restaurado depois."""
        mock_uaz = MagicMock()
        mock_uaz.update_chatbot_settings = AsyncMock()

        with (
            patch("app.workers.disparo_runner.get_uaz_client", return_value=mock_uaz),
            patch("app.workers.disparo_runner._loop_envio", new_callable=AsyncMock),
            patch("app.workers.disparo_runner.settings", MagicMock(handoff_pause_minutes=30)),
        ):
            from app.workers.disparo_runner import run_disparo
            await run_disparo(uuid.uuid4())

        calls = mock_uaz.update_chatbot_settings.call_args_list
        assert len(calls) == 2
        # Primeiro: desativar (stop=0)
        assert calls[0].kwargs["chatbot_stop_when_you_send_msg"] == 0
        # Segundo: restaurar (stop=30)
        assert calls[1].kwargs["chatbot_stop_when_you_send_msg"] == 30

    @pytest.mark.asyncio
    async def test_restore_on_exception(self):
        """Mesmo se _loop_envio crashar, chatbot_stop deve ser restaurado."""
        mock_uaz = MagicMock()
        mock_uaz.update_chatbot_settings = AsyncMock()

        with (
            patch("app.workers.disparo_runner.get_uaz_client", return_value=mock_uaz),
            patch("app.workers.disparo_runner._loop_envio",
                  new_callable=AsyncMock, side_effect=Exception("crash")),
            patch("app.workers.disparo_runner.settings", MagicMock(handoff_pause_minutes=30)),
        ):
            from app.workers.disparo_runner import run_disparo
            with pytest.raises(Exception):
                await run_disparo(uuid.uuid4())

        # Restauração deve ter sido chamada no finally
        calls = mock_uaz.update_chatbot_settings.call_args_list
        assert len(calls) == 2
        assert calls[1].kwargs["chatbot_stop_when_you_send_msg"] == 30


class TestLoopEnvio:
    @pytest.mark.asyncio
    async def test_sends_to_contacts(self):
        """Envia para N contatos com mock uaz."""
        from app.models.disparos import Disparo

        disparo_id = uuid.uuid4()
        disparo = MagicMock(spec=Disparo)
        disparo.id = disparo_id
        disparo.status = "enviando"
        disparo.arquivo_url = "https://drive/file.jpg"
        disparo.arquivo_tipo = "image"
        disparo.legenda = "Teste"
        disparo.filtro_telefones = None
        disparo.filtro_status = None
        disparo.total = 0
        disparo.enviados = 0
        disparo.falhas = 0

        contatos = [
            {"telefone": "5581999", "nome": "João"},
            {"telefone": "5581888", "nome": "Maria"},
            {"telefone": "5581777", "nome": "Pedro"},
        ]

        mock_uaz = MagicMock()
        mock_uaz.send_media = AsyncMock(return_value={"status": "ok"})

        mock_db = AsyncMock()
        mock_db.get.return_value = disparo
        mock_db.add = MagicMock()
        mock_db.scalar.return_value = None  # Nenhum log existente (idempotência)

        with (
            patch("app.workers.disparo_runner.async_session_factory") as mock_sf,
            patch("app.workers.disparo_runner.get_uaz_client", return_value=mock_uaz),
            patch("app.workers.disparo_runner.fetch_contatos", new_callable=AsyncMock, return_value=contatos),
            patch("app.workers.disparo_runner.is_business_hours", return_value=True),
            patch("app.workers.disparo_runner.settings", MagicMock(
                disparos_business_hours_enabled=True,
                disparos_delay_seconds=0,
            )),
            patch("app.workers.disparo_runner.asyncio") as mock_asyncio,
        ):
            mock_asyncio.sleep = AsyncMock()
            mock_sf.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_sf.return_value.__aexit__ = AsyncMock(return_value=False)

            from app.workers.disparo_runner import _loop_envio
            await _loop_envio(disparo_id)

        assert mock_uaz.send_media.await_count == 3
        assert disparo.enviados == 3

    @pytest.mark.asyncio
    async def test_cancellation_stops_loop(self):
        """Status 'cancelado' mid-loop deve parar o runner."""
        from app.models.disparos import Disparo

        disparo_id = uuid.uuid4()
        disparo = MagicMock(spec=Disparo)
        disparo.id = disparo_id
        disparo.arquivo_url = "https://drive/file.jpg"
        disparo.arquivo_tipo = "image"
        disparo.legenda = "Teste"
        disparo.filtro_telefones = None
        disparo.filtro_status = None
        disparo.total = 0
        disparo.enviados = 0
        disparo.falhas = 0

        # Status muda para cancelado após primeiro contato
        status_sequence = ["enviando", "cancelado"]
        type(disparo).status = PropertyMock(side_effect=status_sequence)

        contatos = [
            {"telefone": "5581999", "nome": "João"},
            {"telefone": "5581888", "nome": "Maria"},
        ]

        mock_uaz = MagicMock()
        mock_uaz.send_media = AsyncMock()

        mock_db = AsyncMock()
        mock_db.get.return_value = disparo
        mock_db.add = MagicMock()
        mock_db.scalar.return_value = None

        with (
            patch("app.workers.disparo_runner.async_session_factory") as mock_sf,
            patch("app.workers.disparo_runner.get_uaz_client", return_value=mock_uaz),
            patch("app.workers.disparo_runner.fetch_contatos", new_callable=AsyncMock, return_value=contatos),
            patch("app.workers.disparo_runner.is_business_hours", return_value=True),
            patch("app.workers.disparo_runner.settings", MagicMock(
                disparos_business_hours_enabled=True,
                disparos_delay_seconds=0,
            )),
            patch("app.workers.disparo_runner.asyncio") as mock_asyncio,
        ):
            mock_asyncio.sleep = AsyncMock()
            mock_sf.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_sf.return_value.__aexit__ = AsyncMock(return_value=False)

            from app.workers.disparo_runner import _loop_envio
            await _loop_envio(disparo_id)

        # Deve ter parado no segundo contato (status=cancelado após refresh)
        assert mock_uaz.send_media.await_count <= 1

    @pytest.mark.asyncio
    async def test_idempotency_skips_existing_log(self):
        """Se log já existe para o par (disparo, telefone), pula o envio."""
        from app.models.disparos import Disparo, DisparoLog

        disparo_id = uuid.uuid4()
        disparo = MagicMock(spec=Disparo)
        disparo.id = disparo_id
        disparo.status = "enviando"
        disparo.arquivo_url = "https://drive/file.jpg"
        disparo.arquivo_tipo = "image"
        disparo.legenda = "Teste"
        disparo.filtro_telefones = None
        disparo.filtro_status = None
        disparo.total = 0
        disparo.enviados = 0
        disparo.falhas = 0

        contatos = [{"telefone": "5581999", "nome": "João"}]

        mock_uaz = MagicMock()
        mock_uaz.send_media = AsyncMock()

        mock_db = AsyncMock()
        mock_db.get.return_value = disparo
        mock_db.add = MagicMock()
        # Log já existe para este contato
        mock_db.scalar.return_value = MagicMock(spec=DisparoLog)

        with (
            patch("app.workers.disparo_runner.async_session_factory") as mock_sf,
            patch("app.workers.disparo_runner.get_uaz_client", return_value=mock_uaz),
            patch("app.workers.disparo_runner.fetch_contatos", new_callable=AsyncMock, return_value=contatos),
            patch("app.workers.disparo_runner.is_business_hours", return_value=True),
            patch("app.workers.disparo_runner.settings", MagicMock(
                disparos_business_hours_enabled=True,
                disparos_delay_seconds=0,
            )),
            patch("app.workers.disparo_runner.asyncio") as mock_asyncio,
        ):
            mock_asyncio.sleep = AsyncMock()
            mock_sf.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_sf.return_value.__aexit__ = AsyncMock(return_value=False)

            from app.workers.disparo_runner import _loop_envio
            await _loop_envio(disparo_id)

        # send_media NÃO deve ter sido chamado (log existente → skip)
        mock_uaz.send_media.assert_not_awaited()
