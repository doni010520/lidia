"""Testes para conversation_service e agents."""
from __future__ import annotations

import pytest

from app.services.conversation_service import now_sao_paulo_formatted


class TestDateFormatting:
    def test_returns_portuguese_format(self):
        result = now_sao_paulo_formatted()
        # Deve conter dia da semana em pt-BR
        dias = ["segunda-feira", "terça-feira", "quarta-feira",
                "quinta-feira", "sexta-feira", "sábado", "domingo"]
        assert any(d in result for d in dias), f"Dia da semana não encontrado em: {result}"

        # Deve conter mês em pt-BR
        meses = ["janeiro", "fevereiro", "março", "abril", "maio", "junho",
                 "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
        assert any(m in result for m in meses), f"Mês não encontrado em: {result}"

        # Deve conter " de " (formato pt-BR)
        assert " de " in result

    def test_contains_time(self):
        result = now_sao_paulo_formatted()
        # Deve conter hora:minuto (formato HH:MM)
        parts = result.split()
        time_part = parts[-1]  # último token deve ser HH:MM
        assert ":" in time_part


class TestAgentPromptRendering:
    def test_lidia_prompt_renders_variables(self):
        from app.agents.lidia import build_system_prompt
        result = build_system_prompt(
            nome_usuario="João",
            telefone="5581999999999",
            data_atual="segunda-feira, 01 de janeiro de 2025 10:00",
            dica_rag="Culto domingo 10h",
        )
        assert "João" in result
        assert "5581999999999" in result
        assert "segunda-feira, 01 de janeiro de 2025 10:00" in result
        assert "Culto domingo 10h" in result
        # Deve conter o corpo do prompt
        assert "LidIA" in result

    def test_lidia_prompt_handles_empty_variables(self):
        from app.agents.lidia import build_system_prompt
        result = build_system_prompt(
            nome_usuario="",
            telefone="",
            data_atual="hoje",
            dica_rag="Sem dica de resposta",
        )
        assert "Sem dica de resposta" in result
        assert "LidIA" in result

    def test_lidia_cadastro_prompt_renders(self):
        from app.agents.lidia_cadastro import build_system_prompt
        result = build_system_prompt(
            data_atual="terça-feira, 15 de maio de 2025 14:30",
        )
        assert "terça-feira, 15 de maio de 2025 14:30" in result
        assert "Cadastro" in result or "cadastro" in result

    def test_lidia_prompt_does_not_break_on_json_braces(self):
        """O prompt de 75KB contém { e } em exemplos JSON.
        Jinja2 com {{ }} não deve quebrá-los."""
        from app.agents.lidia import build_system_prompt
        # Não deve lançar exceção
        result = build_system_prompt(
            nome_usuario="Maria",
            telefone="5581888888888",
            data_atual="agora",
            dica_rag="teste",
        )
        assert len(result) > 1000  # prompt é grande (~70k chars)


class TestGetOrCreateContact:
    """Testes para get_or_create_contact (mock de DB)."""

    @pytest.mark.asyncio
    async def test_new_contact_is_committed(self):
        """Novo contato deve receber commit imediato (não apenas flush)."""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_db = AsyncMock()
        # db.add é sync no SQLAlchemy — usar MagicMock para evitar warning
        mock_db.add = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        from app.services.conversation_service import get_or_create_contact
        contact = await get_or_create_contact(mock_db, "5581999999999", "João")

        mock_db.commit.assert_awaited_once()
        mock_db.refresh.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_existing_contact_updates_empty_name(self):
        """Contato existente sem nome deve ser atualizado com nome do webhook."""
        from unittest.mock import AsyncMock, MagicMock
        from app.models.conversation import Contact

        existing = Contact(
            id=1,
            telefone="5581999999999",
            nome=None,
            full_name=None,
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        mock_db.execute.return_value = mock_result

        from app.services.conversation_service import get_or_create_contact
        contact = await get_or_create_contact(mock_db, "5581999999999", "Maria")

        assert contact.nome == "Maria"
        assert contact.full_name == "Maria"
        mock_db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_existing_contact_preserves_existing_name(self):
        """Contato existente COM nome não deve ser sobrescrito."""
        from unittest.mock import AsyncMock, MagicMock
        from app.models.conversation import Contact

        existing = Contact(
            id=1,
            telefone="5581999999999",
            nome="João Original",
            full_name="João Original da Silva",
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        mock_db.execute.return_value = mock_result

        from app.services.conversation_service import get_or_create_contact
        contact = await get_or_create_contact(mock_db, "5581999999999", "Nome Diferente")

        assert contact.nome == "João Original"
        assert contact.full_name == "João Original da Silva"
        # Não deve ter chamado flush (nada mudou)
        mock_db.flush.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_existing_contact_no_name_from_webhook(self):
        """Se webhook não traz nome, contato existente sem nome fica como está."""
        from unittest.mock import AsyncMock, MagicMock
        from app.models.conversation import Contact

        existing = Contact(
            id=1,
            telefone="5581999999999",
            nome=None,
            full_name=None,
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        mock_db.execute.return_value = mock_result

        from app.services.conversation_service import get_or_create_contact
        contact = await get_or_create_contact(mock_db, "5581999999999", None)

        assert contact.nome is None
        mock_db.flush.assert_not_awaited()
