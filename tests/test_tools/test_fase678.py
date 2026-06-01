"""Testes Fases 6-8: notificações, admin routing, handoff, analytics."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.webhook import IncomingMessage


# ── Fase 6: notificar_time_interno ──

class TestNotificarTimeInterno:
    @pytest.mark.asyncio
    async def test_missing_required_fields(self):
        from app.tools.tool_modules.notificar_time_interno import execute
        result = await execute({}, "5581999", AsyncMock())
        assert "obrigatórios" in result

    @pytest.mark.asyncio
    async def test_fallback_duvidas_gerais(self):
        from app.tools.tool_modules.notificar_time_interno import execute
        from app.models.equipes import EquipeResponsavel

        # Primeira chamada: equipe não existe, segunda: fallback
        fallback = EquipeResponsavel(
            id=1, equipe="Dúvidas Gerais",
            telefones_responsaveis=["5581996920063"],
            emails=["paescatedral@gmail.com"],
        )

        mock_db = AsyncMock()
        mock_db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=fallback)),
        ]

        mock_uaz = MagicMock()
        mock_uaz.send_text = AsyncMock(return_value={"status": "ok"})

        with (
            patch("app.tools.tool_modules.notificar_time_interno.get_uaz_client", return_value=mock_uaz),
            patch("app.tools.tool_modules.notificar_time_interno.gmail_client") as mock_gmail,
            patch("app.tools.tool_modules.notificar_time_interno.sheets_client"),
        ):
            mock_gmail.send_email = MagicMock()
            result = await execute(
                {
                    "tipo_situacao": "Dúvida",
                    "prioridade": "media",
                    "equipe_responsavel": "Equipe Inexistente",
                    "nome": "João",
                    "telefone": "5581999",
                    "detalhes": "Teste de fallback",
                },
                "5581999",
                mock_db,
            )

        assert "Dúvidas Gerais" in result
        mock_uaz.send_text.assert_awaited()


# ── Fase 6: resposta_oracao ──

class TestRespostaOracao:
    @pytest.mark.asyncio
    async def test_registra_pedido(self):
        from app.tools.tool_modules.resposta_oracao import execute

        mock_db = AsyncMock()
        # Mock para notificar_time_interno interno
        equipe_mock = MagicMock()
        equipe_mock.scalar_one_or_none.return_value = MagicMock(
            equipe="Oração", telefones_responsaveis=["5581999"], emails=[],
        )
        mock_db.execute.return_value = equipe_mock

        with (
            patch("app.tools.tool_modules.resposta_oracao.sheets_client"),
            patch("app.tools.tool_modules.notificar_time_interno.get_uaz_client",
                  return_value=MagicMock(send_text=AsyncMock())),
            patch("app.tools.tool_modules.notificar_time_interno.sheets_client"),
            patch("app.tools.tool_modules.notificar_time_interno.gmail_client"),
        ):
            result = await execute(
                {"Nome": "Maria", "Telefone": "5581888", "Encorajamento": "Força e fé"},
                "5581888",
                mock_db,
            )

        assert "registrado" in result.lower()


# ── Fase 8: handoff_service ──

class TestHandoffService:
    @pytest.mark.asyncio
    async def test_keyword_off_disables_ai(self, monkeypatch):
        monkeypatch.setattr("app.services.handoff_service.settings", MagicMock(
            handoff_keyword_off="Roberta aqui!",
            handoff_keyword_on="té mais!",
        ))
        from app.services.handoff_service import handle_outgoing
        from app.models.conversation import Contact

        contact = Contact(id=1, telefone="5581999", ai_enabled=True)
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = contact
        mock_db.execute.return_value = mock_result

        msg = IncomingMessage(phone="5581999", text="Roberta aqui! Vou atender", from_me=True)
        await handle_outgoing(msg, mock_db)

        assert contact.ai_enabled is False
        mock_db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_keyword_on_enables_ai(self, monkeypatch):
        monkeypatch.setattr("app.services.handoff_service.settings", MagicMock(
            handoff_keyword_off="Roberta aqui!",
            handoff_keyword_on="té mais!",
        ))
        from app.services.handoff_service import handle_outgoing
        from app.models.conversation import Contact

        contact = Contact(id=1, telefone="5581999", ai_enabled=False)
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = contact
        mock_db.execute.return_value = mock_result

        msg = IncomingMessage(phone="5581999", text="té mais! Obrigada", from_me=True)
        await handle_outgoing(msg, mock_db)

        assert contact.ai_enabled is True
        mock_db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_no_keyword_does_nothing(self, monkeypatch):
        monkeypatch.setattr("app.services.handoff_service.settings", MagicMock(
            handoff_keyword_off="Roberta aqui!",
            handoff_keyword_on="té mais!",
        ))
        from app.services.handoff_service import handle_outgoing
        from app.models.conversation import Contact

        contact = Contact(id=1, telefone="5581999", ai_enabled=True)
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = contact
        mock_db.execute.return_value = mock_result

        msg = IncomingMessage(phone="5581999", text="Ok, pode deixar", from_me=True)
        await handle_outgoing(msg, mock_db)

        assert contact.ai_enabled is True
        mock_db.commit.assert_not_awaited()


# ── Fase 8: analytics_service ──

class TestAnalyticsService:
    def test_start_creates_context(self):
        from app.services.analytics_service import start
        ctx = start(phone="5581999", agent_type="atendimento", input_text="Olá")
        assert ctx.phone == "5581999"
        assert ctx.agent_type == "atendimento"
        assert ctx.start_time > 0

    def test_sentiment_positive(self):
        from app.services.analytics_service import _calc_sentiment
        score = _calc_sentiment("Obrigado, que Deus abençoe! Paz e alegria!")
        assert score > 0.5

    def test_sentiment_negative(self):
        from app.services.analytics_service import _calc_sentiment
        score = _calc_sentiment("Estou com muito medo e angústia, é difícil")
        assert score < 0.5

    def test_sentiment_neutral(self):
        from app.services.analytics_service import _calc_sentiment
        score = _calc_sentiment("Qual o horário do culto?")
        assert score == 0.5

    @pytest.mark.asyncio
    async def test_capture_inserts_analytics(self):
        from app.services.analytics_service import start, capture

        ctx = start(phone="5581999", agent_type="atendimento", input_text="Olá tudo bem")
        mock_db = AsyncMock()

        await capture(ctx, "Olá! Como posso ajudar?", ["buscar_documentos"], mock_db)

        mock_db.execute.assert_awaited_once()
        mock_db.flush.assert_awaited_once()


# ── Registry final ──

class TestRegistryFinal:
    def test_all_16_tools_registered(self):
        from app.tools.registry import ALL_TOOLS
        assert len(ALL_TOOLS) == 16

    def test_lidia_has_13_atendimento_tools(self):
        from app.agents.lidia import TOOLS_ALLOWED, tools_allowed
        assert len(TOOLS_ALLOWED) == 13
        assert len(tools_allowed) == 13
        assert "notificar_time_interno" in TOOLS_ALLOWED
        assert "resposta_oracao" in TOOLS_ALLOWED

    def test_lidia_has_3_admin_tools(self):
        from app.agents.lidia import ADMIN_TOOLS, admin_tools_allowed
        assert len(ADMIN_TOOLS) == 3
        assert "eventos_Lidia" in ADMIN_TOOLS
        assert "informacoes_Lidia" in ADMIN_TOOLS
        assert "treinamento_LidIA" in ADMIN_TOOLS
