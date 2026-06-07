"""Testes para tools da Fase 4 e sheets_sync."""
from __future__ import annotations

from datetime import date, time, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.eventos import EventoPaes
from app.models.plano_leitura import PlanoLeitura


# ── buscar_evento ──

class TestBuscarEvento:
    @pytest.mark.asyncio
    async def test_events_found_by_name(self):
        from app.tools.tool_modules.buscar_evento import execute

        ev = EventoPaes(
            id=1, nome="Cursilho Masculino",
            data_inicio=date(2025, 6, 15), data_final=date(2025, 6, 17),
            hora=time(19, 0), local="Sede PAES",
            descricao="Retiro", valor="R$ 200",
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [ev]
        mock_db.execute.return_value = mock_result

        result = await execute({"nome_evento": "Cursilho"}, "5581999", mock_db)

        assert "Cursilho Masculino" in result
        assert "15/06/2025" in result
        assert "19:00" in result
        assert "Sede PAES" in result
        assert "1 evento" in result

    @pytest.mark.asyncio
    async def test_events_found_by_date_range(self):
        from app.tools.tool_modules.buscar_evento import execute

        ev1 = EventoPaes(id=1, nome="Culto Dominical", data_inicio=date(2025, 6, 8))
        ev2 = EventoPaes(id=2, nome="Célula", data_inicio=date(2025, 6, 10))

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [ev1, ev2]
        mock_db.execute.return_value = mock_result

        result = await execute(
            {"data_inicio": "2025-06-01", "data_fim": "2025-06-30"},
            "5581999",
            mock_db,
        )

        assert "2 evento" in result
        assert "Culto Dominical" in result
        assert "Célula" in result

    @pytest.mark.asyncio
    async def test_fallback_rag_when_empty(self):
        from app.tools.tool_modules.buscar_evento import execute

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        with patch("app.tools.tool_modules.buscar_evento.RAGService") as MockRAG:
            instance = MockRAG.return_value
            instance.search = AsyncMock(return_value=[])
            instance.format_chunks = MagicMock(return_value="Sem dica de resposta")

            result = await execute({"nome_evento": "Happening"}, "5581999", mock_db)

        assert "Nenhum evento encontrado" in result


# ── plano_de_leitura ──

class TestPlanoLeitura:
    @pytest.mark.asyncio
    async def test_leitura_de_hoje(self):
        from app.tools.tool_modules.plano_de_leitura import execute
        from datetime import datetime
        from zoneinfo import ZoneInfo

        today = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
        row = PlanoLeitura(
            id=1, data=today,
            livro="Gênesis", leitura="Gn 1-3",
            capitulos="1-3", semana=1,
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [row]
        mock_db.execute.return_value = mock_result

        result = await execute({"descricao": "leitura de hoje"}, "5581999", mock_db)

        assert "Gênesis" in result
        assert "Gn 1-3" in result
        assert "hoje" in result.lower()

    @pytest.mark.asyncio
    async def test_leitura_da_semana(self):
        from app.tools.tool_modules.plano_de_leitura import execute
        from datetime import datetime
        from zoneinfo import ZoneInfo

        today = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
        rows = [
            PlanoLeitura(id=i, data=today + timedelta(days=i), leitura=f"Cap {i}", livro="Gênesis")
            for i in range(7)
        ]

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = rows
        mock_db.execute.return_value = mock_result

        result = await execute({"descricao": "cronograma da semana"}, "5581999", mock_db)

        assert "semana" in result.lower()

    @pytest.mark.asyncio
    async def test_nenhuma_leitura_cadastrada(self):
        from app.tools.tool_modules.plano_de_leitura import execute

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        result = await execute({"descricao": "leitura de hoje"}, "5581999", mock_db)

        assert "Não há leitura" in result


# ── novos_convertidos ──

class TestNovosConvertidos:
    @pytest.mark.asyncio
    async def test_registra_convertido(self):
        from app.tools.tool_modules.novos_convertidos import execute

        mock_db = AsyncMock()
        result = await execute(
            {"telefone": "5581999999999", "nome": "João"},
            "5581999999999",
            mock_db,
        )

        assert "registrada" in result.lower()
        assert "João" in result
        mock_db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_nome_obrigatorio(self):
        from app.tools.tool_modules.novos_convertidos import execute

        result = await execute({"telefone": "5581999"}, "5581999", AsyncMock())
        assert "obrigatório" in result


# ── sheets_sync ──

class TestSheetsSync:
    @pytest.mark.asyncio
    async def test_sync_eventos_skips_when_no_sheet_id(self, monkeypatch):
        monkeypatch.setattr("app.workers.sheets_sync.settings", MagicMock(sheets_eventos_id=""))
        from app.workers.sheets_sync import sync_eventos
        result = await sync_eventos()
        assert result == 0

    @pytest.mark.asyncio
    async def test_sync_plano_skips_when_no_sheet_id(self, monkeypatch):
        monkeypatch.setattr("app.workers.sheets_sync.settings", MagicMock(sheets_plano_leitura_id=""))
        from app.workers.sheets_sync import sync_plano_leitura
        result = await sync_plano_leitura()
        assert result == 0

    @pytest.mark.asyncio
    async def test_sync_informacoes_skips_when_no_sheet_id(self, monkeypatch):
        monkeypatch.setattr("app.workers.sheets_sync.settings", MagicMock(sheets_informacoes_id=""))
        from app.workers.sheets_sync import sync_informacoes
        result = await sync_informacoes()
        assert result == 0

    def test_parse_date_iso(self):
        from app.workers.sheets_sync import _parse_date
        assert _parse_date("2025-06-15") == date(2025, 6, 15)

    def test_parse_date_br(self):
        from app.workers.sheets_sync import _parse_date
        assert _parse_date("15/06/2025") == date(2025, 6, 15)

    def test_parse_date_invalid(self):
        from app.workers.sheets_sync import _parse_date
        assert _parse_date("abc") is None
        assert _parse_date("") is None
        assert _parse_date(None) is None

    def test_parse_time(self):
        from app.workers.sheets_sync import _parse_time
        assert _parse_time("19:30") == time(19, 30)
        assert _parse_time("8:00") == time(8, 0)
        assert _parse_time("") is None
        assert _parse_time(None) is None

    @pytest.mark.asyncio
    async def test_sync_eventos_idempotent_upsert(self, monkeypatch):
        """Rodar sync 2× com mesma row não duplica — ON CONFLICT (sheets_row_id) DO UPDATE."""
        monkeypatch.setattr("app.workers.sheets_sync.settings", MagicMock(
            sheets_eventos_id="fake_sheet_id",
        ))

        fake_rows = [
            {"Nome": "Culto", "Data": "2025-06-15", "Local": "Sede", "_row_number": 2},
            {"Nome": "Culto", "Data": "2025-06-15", "Local": "Sede", "_row_number": 2},
        ]

        with patch("app.workers.sheets_sync.sheets_client") as mock_sheets:
            mock_sheets.read_all.return_value = fake_rows

            mock_db = AsyncMock()
            mock_db.add = MagicMock()
            mock_session_factory = MagicMock()
            mock_session_factory.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session_factory.__aexit__ = AsyncMock(return_value=False)
            monkeypatch.setattr("app.workers.sheets_sync.async_session_factory", MagicMock(return_value=mock_session_factory))

            from app.workers.sheets_sync import sync_eventos
            result = await sync_eventos()

            assert result == 2
            # Verificar que o SQL contém ON CONFLICT (sheets_row_id) DO UPDATE
            calls = mock_db.execute.call_args_list
            for call in calls:
                sql_str = str(call[0][0].text)
                if "INSERT INTO eventos_paes" in sql_str:
                    assert "ON CONFLICT (sheets_row_id) DO UPDATE" in sql_str
                    assert "DO NOTHING" not in sql_str


# ── registry atualizado ──

class TestRegistryPhase4:
    def test_all_tools_registered(self):
        from app.tools.registry import ALL_TOOLS
        assert len(ALL_TOOLS) == 21

    def test_lidia_atendimento_tools(self):
        from app.agents.lidia import TOOLS_ALLOWED, tools_allowed
        assert len(TOOLS_ALLOWED) == 17
        assert len(tools_allowed) == 17
        assert "buscar_evento" in TOOLS_ALLOWED
        assert "plano_de_leitura" in TOOLS_ALLOWED
        assert "novos_convertidos" in TOOLS_ALLOWED
        assert "PAES_listar_arquivos" in TOOLS_ALLOWED
