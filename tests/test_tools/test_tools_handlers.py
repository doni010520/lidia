"""Testes para tools: registry, handlers, e cada tool module."""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tools.registry import ALL_TOOLS, get_tools


class TestRegistry:
    def test_all_tools_registered(self):
        from app.tools.registry import ALL_TOOLS
        assert len(ALL_TOOLS) == 16

    def test_get_tools_filters_by_name(self):
        result = get_tools(["buscar_documentos", "cadastrar_contato"])
        assert len(result) == 2
        names = {t["function"]["name"] for t in result}
        assert names == {"buscar_documentos", "cadastrar_contato"}

    def test_get_tools_ignores_unknown(self):
        result = get_tools(["buscar_documentos", "tool_inexistente"])
        assert len(result) == 1

    def test_get_tools_empty_list(self):
        result = get_tools([])
        assert result == []

    def test_each_tool_has_valid_schema(self):
        for name, schema in ALL_TOOLS.items():
            assert schema["type"] == "function"
            func = schema["function"]
            assert func["name"] == name
            assert "description" in func
            assert "parameters" in func
            assert func["parameters"]["type"] == "object"


class TestHandlers:
    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self):
        from app.tools.handlers import handle_tool_call
        result = await handle_tool_call("tool_fantasma", {}, "5581999")
        assert "não encontrada" in result

    @pytest.mark.asyncio
    async def test_dispatcher_routes_correctly(self):
        """Verifica que o dispatcher chama o módulo certo."""
        from app.tools.handlers import handle_tool_call

        # Mock do módulo buscar_documentos
        with patch("app.tools.tool_modules.buscar_documentos.execute", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = "Resultado da busca"
            result = await handle_tool_call(
                "buscar_documentos",
                {"query": "horário do culto"},
                "5581999",
                db=AsyncMock(),
            )
            assert result == "Resultado da busca"
            mock_exec.assert_awaited_once()


class TestBuscarDocumentos:
    @pytest.mark.asyncio
    async def test_empty_query_returns_error(self):
        from app.tools.tool_modules.buscar_documentos import execute
        result = await execute({}, "5581999", AsyncMock())
        assert "obrigatório" in result

    @pytest.mark.asyncio
    async def test_calls_rag_search(self):
        from app.tools.tool_modules.buscar_documentos import execute
        with patch("app.tools.tool_modules.buscar_documentos.RAGService") as MockRAG:
            instance = MockRAG.return_value
            instance.search = AsyncMock(return_value=[])
            instance.format_chunks = MagicMock(return_value="Sem dica de resposta")

            result = await execute({"query": "culto"}, "5581999", AsyncMock())
            assert result == "Sem dica de resposta"
            instance.search.assert_awaited_once()


class TestCadastrarContato:
    @pytest.mark.asyncio
    async def test_missing_nome_returns_error(self):
        from app.tools.tool_modules.cadastrar_contato import execute
        result = await execute({"telefone": "5581999"}, "5581999", AsyncMock())
        assert "obrigatório" in result

    @pytest.mark.asyncio
    async def test_creates_new_contact(self):
        from app.tools.tool_modules.cadastrar_contato import execute

        mock_db = AsyncMock()
        mock_db.add = MagicMock()  # db.add é sync no SQLAlchemy
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await execute(
            {"nome": "João Silva", "telefone": "5581999999999", "status": "membro"},
            "5581999999999",
            mock_db,
        )

        assert "criado" in result.lower()
        assert "João Silva" in result
        assert "membro" in result
        mock_db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_updates_existing_contact(self):
        from app.tools.tool_modules.cadastrar_contato import execute
        from app.models.conversation import Contact

        existing = Contact(
            id=1,
            telefone="5581999999999",
            nome="João",
            cadastro_completo=False,
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        mock_db.execute.return_value = mock_result

        result = await execute(
            {"nome": "João Silva", "telefone": "5581999999999", "email": "joao@test.com"},
            "5581999999999",
            mock_db,
        )

        assert "atualizado" in result.lower()
        assert existing.cadastro_completo is True
        assert existing.email == "joao@test.com"

    @pytest.mark.asyncio
    async def test_parses_birthday(self):
        from app.tools.tool_modules.cadastrar_contato import execute
        from app.models.conversation import Contact

        existing = Contact(id=1, telefone="5581999999999", nome="Ana")

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        mock_db.execute.return_value = mock_result

        result = await execute(
            {"nome": "Ana Maria", "telefone": "5581999999999", "aniversario": "2000-03-15"},
            "5581999999999",
            mock_db,
        )

        assert existing.aniversario == date(2000, 3, 15)
        assert "15/03/2000" in result


class TestCadastrarAniversario:
    @pytest.mark.asyncio
    async def test_missing_data_returns_error(self):
        from app.tools.tool_modules.cadastrar_aniversario import execute
        result = await execute({"telefone": "5581999"}, "5581999", AsyncMock())
        assert "obrigatório" in result

    @pytest.mark.asyncio
    async def test_invalid_date_returns_error(self):
        from app.tools.tool_modules.cadastrar_aniversario import execute
        result = await execute(
            {"telefone": "5581999", "data": "32/13/2000"},
            "5581999",
            AsyncMock(),
        )
        assert "inválido" in result

    @pytest.mark.asyncio
    async def test_contact_not_found(self):
        from app.tools.tool_modules.cadastrar_aniversario import execute

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await execute(
            {"telefone": "5581000000000", "data": "2000-05-20"},
            "5581000000000",
            mock_db,
        )
        assert "não encontrado" in result

    @pytest.mark.asyncio
    async def test_updates_birthday(self):
        from app.tools.tool_modules.cadastrar_aniversario import execute
        from app.models.conversation import Contact

        contact = Contact(id=1, telefone="5581999999999", nome="Ana")

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = contact
        mock_db.execute.return_value = mock_result

        result = await execute(
            {"telefone": "5581999999999", "data": "2000-05-20"},
            "5581999999999",
            mock_db,
        )

        assert contact.aniversario == date(2000, 5, 20)
        assert "20/05/2000" in result


class TestAtualizarSobrenome:
    @pytest.mark.asyncio
    async def test_missing_nome_completo(self):
        from app.tools.tool_modules.atualizar_sobrenome import execute
        result = await execute({"telefone": "5581999"}, "5581999", AsyncMock())
        assert "obrigatório" in result

    @pytest.mark.asyncio
    async def test_updates_full_name(self):
        from app.tools.tool_modules.atualizar_sobrenome import execute
        from app.models.conversation import Contact

        contact = Contact(id=1, telefone="5581999999999", nome="Ana", full_name="Ana")

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = contact
        mock_db.execute.return_value = mock_result

        result = await execute(
            {"telefone": "5581999999999", "nome_completo": "Ana Maria Silva"},
            "5581999999999",
            mock_db,
        )

        assert contact.full_name == "Ana Maria Silva"
        assert contact.nome == "Ana"  # nome curto = primeiro nome
        assert "Ana Maria Silva" in result

    @pytest.mark.asyncio
    async def test_contact_not_found(self):
        from app.tools.tool_modules.atualizar_sobrenome import execute

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await execute(
            {"telefone": "5581000", "nome_completo": "Teste"},
            "5581000",
            mock_db,
        )
        assert "não encontrado" in result


class TestExcluirUsuario:
    @pytest.mark.asyncio
    async def test_contact_not_found(self):
        from app.tools.tool_modules.excluir_usuario import execute

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await execute({"telefone": "5581000"}, "5581000", mock_db)
        assert "não encontrado" in result

    @pytest.mark.asyncio
    async def test_deletes_contact_and_messages(self):
        from app.tools.tool_modules.excluir_usuario import execute
        from app.models.conversation import Contact

        contact = Contact(
            id=1, telefone="5581999999999",
            nome="Ana", full_name="Ana Maria Silva",
        )

        # Mock: primeira chamada retorna contato, próximas são deletes
        mock_db = AsyncMock()
        select_result = MagicMock()
        select_result.scalar_one_or_none.return_value = contact

        delete_msgs_result = MagicMock()
        delete_msgs_result.rowcount = 42

        delete_contact_result = MagicMock()

        mock_db.execute.side_effect = [
            select_result,
            delete_msgs_result,
            delete_contact_result,
        ]

        result = await execute({"telefone": "5581999999999"}, "5581999999999", mock_db)

        assert "excluídos" in result.lower() or "Dados excluídos" in result
        assert "Ana Maria Silva" in result
        assert "42" in result
        mock_db.commit.assert_awaited_once()


class TestAgentsToolsWiring:
    def test_lidia_has_11_tools(self):
        from app.agents.lidia import TOOLS_ALLOWED, tools_allowed
        assert len(TOOLS_ALLOWED) == 13
        assert len(tools_allowed) == 13
        assert "buscar_documentos" in TOOLS_ALLOWED
        assert "excluir_usuario" in TOOLS_ALLOWED
        assert "buscar_evento" in TOOLS_ALLOWED
        assert "plano_de_leitura" in TOOLS_ALLOWED
        assert "PAES_listar_arquivos" in TOOLS_ALLOWED

    def test_lidia_cadastro_has_1_tool(self):
        from app.agents.lidia_cadastro import TOOLS_ALLOWED, tools_allowed
        assert len(TOOLS_ALLOWED) == 1
        assert TOOLS_ALLOWED[0] == "cadastrar_contato"
        assert len(tools_allowed) == 1

    def test_tools_have_valid_openai_schema(self):
        from app.agents.lidia import tools_allowed
        for tool in tools_allowed:
            assert tool["type"] == "function"
            assert "name" in tool["function"]
            assert "parameters" in tool["function"]
