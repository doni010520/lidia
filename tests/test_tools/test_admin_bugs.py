"""Testes anti-regressão: admin routing e eventos_lidia duplicação."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.webhook import IncomingMessage


class TestAdminRoutingEndToEnd:
    """Verifica que comandos admin são interceptados antes do pipeline normal."""

    @pytest.mark.asyncio
    async def test_treino_command_dispatches_to_handler(self, monkeypatch):
        """Admin envia 'TreinoIA12 ...' → chama treinamento_lidia.execute, NÃO o agente normal."""
        monkeypatch.setattr("app.routers.admin_router.settings",
                           MagicMock(admin_phones_list=["5581999999999"]))

        msg = IncomingMessage(
            phone="5581999999999",
            text="TreinoIA12 atualizar base",
            message_id="ADM001",
        )

        mock_uaz = MagicMock()
        mock_uaz.send_text = AsyncMock(return_value={"status": "ok"})
        mock_uaz.send_presence = AsyncMock()
        mock_uaz.download_message = AsyncMock()

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        # get_or_create_contact mock
        from app.models.conversation import Contact
        contact = Contact(
            id=1, telefone="5581999999999", nome="Admin",
            ai_enabled=True, cadastro_completo=True, is_blocked=False,
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = contact
        mock_db.execute.return_value = mock_result

        with (
            patch("app.services.conversation_service.get_uaz_client", return_value=mock_uaz),
            patch("app.tools.tool_modules.treinamento_lidia.execute", new_callable=AsyncMock) as mock_treino,
        ):
            mock_treino.return_value = "Re-vectorização iniciada."

            from app.services.conversation_service import process_message
            await process_message(msg, mock_db)

        # treinamento_lidia.execute DEVE ter sido chamado
        mock_treino.assert_awaited_once()
        # uaz.send_text DEVE ter enviado a resposta de confirmação
        mock_uaz.send_text.assert_awaited()

    @pytest.mark.asyncio
    async def test_non_admin_command_ignored(self, monkeypatch):
        """Número fora da lista admin → comando NÃO interceptado, vai para pipeline normal."""
        monkeypatch.setattr("app.routers.admin_router.settings",
                           MagicMock(admin_phones_list=["5581111111111"]))

        msg = IncomingMessage(
            phone="5581999999999",
            text="TreinoIA12 hack attempt",
            message_id="ADM002",
        )

        # parse_admin_command deve retornar None para não-admin
        from app.routers.admin_router import parse_admin_command
        result = parse_admin_command(msg)
        assert result is None

    @pytest.mark.asyncio
    async def test_limpar_command_deletes_messages(self, monkeypatch):
        """Admin envia 'Limpar dados 5581888...' → deleta mensagens do telefone alvo."""
        monkeypatch.setattr("app.routers.admin_router.settings",
                           MagicMock(admin_phones_list=["5581999999999"]))

        msg = IncomingMessage(
            phone="5581999999999",
            text="Limpar dados 5581888888888",
            message_id="ADM003",
        )

        mock_uaz = MagicMock()
        mock_uaz.send_text = AsyncMock(return_value={"status": "ok"})

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        # Contact mock
        from app.models.conversation import Contact
        contact = Contact(
            id=1, telefone="5581999999999", nome="Admin",
            ai_enabled=True, cadastro_completo=True, is_blocked=False,
        )
        select_result = MagicMock()
        select_result.scalar_one_or_none.return_value = contact
        delete_result = MagicMock()
        delete_result.rowcount = 15
        mock_db.execute.side_effect = [select_result, delete_result]

        with patch("app.services.conversation_service.get_uaz_client", return_value=mock_uaz):
            from app.services.conversation_service import process_message
            await process_message(msg, mock_db)

        # Deve ter enviado confirmação com contagem
        call_args = mock_uaz.send_text.call_args_list
        assert any("15" in str(c) for c in call_args)


class TestEventosLidiaIdempotency:
    @pytest.mark.asyncio
    async def test_cadastrar_twice_same_name_no_duplicate(self):
        """Cadastrar evento 2× com mesmo nome+data → UPSERT, não duplica."""
        from app.tools.tool_modules.eventos_lidia import execute

        mock_db = AsyncMock()

        # Primeira chamada
        result1 = await execute(
            {"funcao": "cadastrar", "Nome": "Culto Especial", "Data_inicio": "2025-07-01"},
            "5581999",
            mock_db,
        )
        assert "cadastrado" in result1.lower()

        # Segunda chamada idêntica
        result2 = await execute(
            {"funcao": "cadastrar", "Nome": "Culto Especial", "Data_inicio": "2025-07-01"},
            "5581999",
            mock_db,
        )
        assert "cadastrado" in result2.lower()

        # Verificar que o SQL contém ON CONFLICT DO UPDATE (não DO NOTHING)
        for call in mock_db.execute.call_args_list:
            sql_str = str(call[0][0].text)
            if "INSERT INTO eventos_paes" in sql_str:
                assert "ON CONFLICT (sheets_row_id) DO UPDATE" in sql_str
                assert "DO NOTHING" not in sql_str

    @pytest.mark.asyncio
    async def test_cadastrar_generates_deterministic_row_id(self):
        """sheets_row_id deve ser determinístico baseado em nome+data."""
        from app.tools.tool_modules.eventos_lidia import execute

        mock_db = AsyncMock()

        await execute(
            {"funcao": "cadastrar", "Nome": "Cursilho", "Data_inicio": "2025-08-15"},
            "5581999",
            mock_db,
        )

        # Verificar que sheets_row_id foi passado e é determinístico
        for call in mock_db.execute.call_args_list:
            if len(call[0]) > 1:
                params = call[0][1]
                if "sheets_row_id" in params:
                    assert params["sheets_row_id"] == "admin:cursilho:2025-08-15"

    @pytest.mark.asyncio
    async def test_atualizar_uses_update_not_insert(self):
        """Atualizar usa UPDATE explícito, não INSERT."""
        from app.tools.tool_modules.eventos_lidia import execute

        mock_db = AsyncMock()
        update_result = MagicMock()
        update_result.rowcount = 1
        mock_db.execute.return_value = update_result

        result = await execute(
            {"funcao": "atualizar", "Nome": "Culto", "Local": "Nave principal"},
            "5581999",
            mock_db,
        )

        assert "atualizado" in result.lower()
        # Verificar que o SQL é UPDATE, não INSERT
        sql_str = str(mock_db.execute.call_args[0][0].text)
        assert "UPDATE eventos_paes" in sql_str
        assert "INSERT" not in sql_str

    @pytest.mark.asyncio
    async def test_atualizar_nao_encontrado(self):
        """Atualizar evento inexistente retorna mensagem clara."""
        from app.tools.tool_modules.eventos_lidia import execute

        mock_db = AsyncMock()
        update_result = MagicMock()
        update_result.rowcount = 0
        mock_db.execute.return_value = update_result

        result = await execute(
            {"funcao": "atualizar", "Nome": "Inexistente"},
            "5581999",
            mock_db,
        )

        assert "Nenhum evento encontrado" in result
