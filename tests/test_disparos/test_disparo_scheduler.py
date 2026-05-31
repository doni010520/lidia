"""Testes para disparo_scheduler."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestCheckScheduled:
    @pytest.mark.asyncio
    async def test_skips_outside_business_hours(self):
        with (
            patch("app.workers.disparo_scheduler.settings", MagicMock(
                disparos_business_hours_enabled=True,
            )),
            patch("app.workers.disparo_scheduler.is_business_hours", return_value=False),
        ):
            from app.workers.disparo_scheduler import check_scheduled_disparos
            result = await check_scheduled_disparos()
        assert result == 0

    @pytest.mark.asyncio
    async def test_skips_if_already_sending(self):
        mock_db = AsyncMock()
        mock_db.scalar.return_value = 1  # Já tem enviando

        with (
            patch("app.workers.disparo_scheduler.settings", MagicMock(
                disparos_business_hours_enabled=False,
            )),
            patch("app.workers.disparo_scheduler.async_session_factory") as mock_sf,
        ):
            mock_sf.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_sf.return_value.__aexit__ = AsyncMock(return_value=False)

            from app.workers.disparo_scheduler import check_scheduled_disparos
            result = await check_scheduled_disparos()

        assert result == 0

    @pytest.mark.asyncio
    async def test_picks_up_scheduled_disparo(self):
        from app.models.disparos import Disparo

        disparo = MagicMock(spec=Disparo)
        disparo.id = uuid.uuid4()
        disparo.status = "agendado"

        mock_db = AsyncMock()
        mock_db.scalar.return_value = 0  # Nenhum enviando

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = disparo
        mock_db.execute.return_value = mock_result

        with (
            patch("app.workers.disparo_scheduler.settings", MagicMock(
                disparos_business_hours_enabled=False,
            )),
            patch("app.workers.disparo_scheduler.async_session_factory") as mock_sf,
            patch("app.workers.disparo_scheduler.asyncio") as mock_asyncio,
        ):
            mock_sf.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_sf.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_asyncio.create_task = MagicMock()

            from app.workers.disparo_scheduler import check_scheduled_disparos
            result = await check_scheduled_disparos()

        assert result == 1
        assert disparo.status == "enviando"
        mock_asyncio.create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_pending_disparo(self):
        mock_db = AsyncMock()
        mock_db.scalar.return_value = 0

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with (
            patch("app.workers.disparo_scheduler.settings", MagicMock(
                disparos_business_hours_enabled=False,
            )),
            patch("app.workers.disparo_scheduler.async_session_factory") as mock_sf,
        ):
            mock_sf.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_sf.return_value.__aexit__ = AsyncMock(return_value=False)

            from app.workers.disparo_scheduler import check_scheduled_disparos
            result = await check_scheduled_disparos()

        assert result == 0
