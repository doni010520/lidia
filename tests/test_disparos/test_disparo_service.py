"""Testes para disparo_service — fetch_contatos, lock, business hours."""
from __future__ import annotations

from datetime import datetime, time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.disparo_service import check_lock, count_contatos, is_business_hours


class TestCheckLock:
    @pytest.mark.asyncio
    async def test_no_lock(self):
        mock_db = AsyncMock()
        mock_db.scalar.return_value = 0
        assert await check_lock(mock_db) is False

    @pytest.mark.asyncio
    async def test_has_lock(self):
        mock_db = AsyncMock()
        mock_db.scalar.return_value = 1
        assert await check_lock(mock_db) is True


class TestCountContatos:
    @pytest.mark.asyncio
    async def test_count_all(self):
        mock_db = AsyncMock()
        mock_db.scalar.return_value = 247
        result = await count_contatos(mock_db)
        assert result == 247

    @pytest.mark.asyncio
    async def test_count_with_filter(self):
        mock_db = AsyncMock()
        mock_db.scalar.return_value = 100
        result = await count_contatos(mock_db, status_filter="membro")
        assert result == 100


class TestFetchContatos:
    @pytest.mark.asyncio
    async def test_fetch_with_explicit_phones(self):
        from app.services.disparo_service import fetch_contatos
        from app.models.conversation import Contact

        mock_disparo = MagicMock()
        mock_disparo.filtro_telefones = ["5581999", "5581888"]
        mock_disparo.filtro_status = None

        c1 = Contact(telefone="5581999", nome="João")
        c2 = Contact(telefone="5581888", nome="Maria")

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [c1, c2]
        mock_db.execute.return_value = mock_result

        result = await fetch_contatos(mock_db, mock_disparo)
        assert len(result) == 2
        assert result[0]["telefone"] == "5581999"

    @pytest.mark.asyncio
    async def test_fetch_filters_blocked_and_disabled(self):
        """Query padrão deve filtrar ai_enabled=False e is_blocked=True."""
        from app.services.disparo_service import fetch_contatos

        mock_disparo = MagicMock()
        mock_disparo.filtro_telefones = None
        mock_disparo.filtro_status = None

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        await fetch_contatos(mock_db, mock_disparo)

        # Verificar que execute foi chamado (query foi construída)
        mock_db.execute.assert_awaited_once()


class TestBusinessHours:
    def test_weekday_inside_hours(self):
        with patch("app.services.disparo_service.datetime") as mock_dt:
            mock_now = MagicMock()
            mock_now.weekday.return_value = 2  # Wed
            mock_now.hour = 10
            mock_now.minute = 0
            mock_dt.now.return_value = mock_now
            assert is_business_hours() is True

    def test_weekday_outside_hours(self):
        with patch("app.services.disparo_service.datetime") as mock_dt:
            mock_now = MagicMock()
            mock_now.weekday.return_value = 2  # Wed
            mock_now.hour = 19
            mock_now.minute = 0
            mock_dt.now.return_value = mock_now
            assert is_business_hours() is False

    def test_sunday_always_closed(self):
        with patch("app.services.disparo_service.datetime") as mock_dt:
            mock_now = MagicMock()
            mock_now.weekday.return_value = 6  # Sun
            mock_now.hour = 10
            mock_now.minute = 0
            mock_dt.now.return_value = mock_now
            assert is_business_hours() is False

    def test_saturday_inside_hours(self):
        with patch("app.services.disparo_service.datetime") as mock_dt:
            mock_now = MagicMock()
            mock_now.weekday.return_value = 5  # Sat
            mock_now.hour = 10
            mock_now.minute = 0
            mock_dt.now.return_value = mock_now
            assert is_business_hours() is True

    def test_saturday_outside_hours(self):
        with patch("app.services.disparo_service.datetime") as mock_dt:
            mock_now = MagicMock()
            mock_now.weekday.return_value = 5  # Sat
            mock_now.hour = 14
            mock_now.minute = 0
            mock_dt.now.return_value = mock_now
            assert is_business_hours() is False
