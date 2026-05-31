"""Testes para API de Eventos — 6 testes mínimos do SPEC."""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.eventos import EventoPaes


def _make_evento(**overrides) -> MagicMock:
    defaults = dict(
        id=1, nome="Cursilho", descricao="Retiro", local="Sede",
        data_inicio=date.today() + timedelta(days=30),
        data_final=date.today() + timedelta(days=32),
        hora=None, valor="R$ 200", link=None, media=None,
        origem="painel", sheets_row_id="painel:abc-123",
        created_at=MagicMock(), updated_at=MagicMock(),
    )
    defaults.update(overrides)
    ev = MagicMock(spec=EventoPaes)
    for k, v in defaults.items():
        setattr(ev, k, v)
    return ev


class TestCreateEventoOrigemPainel:
    @pytest.mark.asyncio
    async def test_create_sets_origem_painel_and_sheets_row_id(self):
        from app.api.eventos import create_evento
        from app.schemas.eventos import EventoCreate

        body = EventoCreate(nome="Culto Especial", data_inicio=date(2026, 8, 15))
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_user = MagicMock(username="admin")

        # Capturar o objeto adicionado
        added = []
        mock_db.add.side_effect = lambda obj: added.append(obj)

        await create_evento(body, db=mock_db, user=mock_user)

        assert len(added) == 1
        ev = added[0]
        assert ev.origem == "painel"
        assert ev.sheets_row_id.startswith("painel:")
        assert ev.nome == "Culto Especial"
        mock_db.commit.assert_awaited_once()


class TestListFiltraPorPeriodo:
    @pytest.mark.asyncio
    async def test_futuros_only(self):
        from app.api.eventos import list_eventos

        future = _make_evento(id=1, data_inicio=date.today() + timedelta(days=10))
        past = _make_evento(id=2, data_inicio=date.today() - timedelta(days=10), data_final=date.today() - timedelta(days=8))

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [future]
        mock_db.execute.return_value = mock_result

        result = await list_eventos(periodo="futuros", origem="todos", db=mock_db, _user=MagicMock())
        assert len(result) == 1
        assert result[0].id == 1


class TestListFiltraPorOrigem:
    @pytest.mark.asyncio
    async def test_painel_only(self):
        from app.api.eventos import list_eventos

        ev = _make_evento(id=1, origem="painel")

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [ev]
        mock_db.execute.return_value = mock_result

        result = await list_eventos(periodo="todos", origem="painel", db=mock_db, _user=MagicMock())
        assert len(result) == 1
        assert result[0].origem == "painel"


class TestPatchEventoSheetsSemConfirmar:
    @pytest.mark.asyncio
    async def test_retorna_409(self):
        from app.api.eventos import update_evento
        from app.schemas.eventos import EventoUpdate
        from fastapi import HTTPException

        ev = _make_evento(id=1, origem="sheets", sheets_row_id="sheets:row2")
        mock_db = AsyncMock()
        mock_db.get.return_value = ev

        body = EventoUpdate(nome="Novo Nome")  # sem confirmar_descolar

        with pytest.raises(HTTPException) as exc:
            await update_evento(1, body, db=mock_db, _user=MagicMock())

        assert exc.value.status_code == 409
        assert exc.value.detail["error"] == "evento_de_planilha"


class TestPatchEventoSheetsComConfirmar:
    @pytest.mark.asyncio
    async def test_muda_origem_para_painel(self):
        from app.api.eventos import update_evento
        from app.schemas.eventos import EventoUpdate

        ev = _make_evento(id=1, origem="sheets", sheets_row_id="sheets:row2")
        mock_db = AsyncMock()
        mock_db.get.return_value = ev

        body = EventoUpdate(nome="Novo Nome", confirmar_descolar=True)
        result = await update_evento(1, body, db=mock_db, _user=MagicMock())

        assert result.origem == "painel"
        assert result.sheets_row_id.startswith("painel:")
        assert result.nome == "Novo Nome"
        mock_db.commit.assert_awaited()


class TestDeleteEventoSheetsSemConfirmar:
    @pytest.mark.asyncio
    async def test_retorna_409(self):
        from app.api.eventos import delete_evento
        from fastapi import HTTPException

        ev = _make_evento(id=1, origem="sheets")
        mock_db = AsyncMock()
        mock_db.get.return_value = ev

        with pytest.raises(HTTPException) as exc:
            await delete_evento(1, confirmar_descolar=False, db=mock_db, _user=MagicMock())

        assert exc.value.status_code == 409
        assert exc.value.detail["error"] == "evento_de_planilha"
