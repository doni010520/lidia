"""buscar_evento contra a Diacon (fonte de verdade da agenda).

Substitui os testes antigos da era do banco local (eventos_paes), que
falhavam desde a migração pra Diacon com "integração Diacon não configurada".
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from app.services.rag_service import RAGChunk, RAGService
from app.tools.tool_modules import buscar_evento as be

_SP = ZoneInfo("America/Sao_Paulo")


def _ev(title, dia: date, *, reg=False, slug="x", type_="Encontro"):
    return {
        "title": title,
        "starts_at": f"{dia.isoformat()}T19:00:00-03:00",
        "ends_at": f"{dia.isoformat()}T21:00:00-03:00",
        "type": type_,
        "venue": "Templo Principal",
        "description_short": None,
        "has_registration": reg,
        "registration_url": f"https://diacon.ia.br/e/{slug}",
    }


@pytest.fixture
def diacon(monkeypatch):
    fake = AsyncMock(return_value={"events": []})
    monkeypatch.setattr(be.diacon_client, "is_enabled", lambda: True)
    monkeypatch.setattr(be.diacon_client, "events_upcoming", fake)
    return fake


class TestJanelaDaAgenda:
    @pytest.mark.asyncio
    async def test_pede_90_dias_sem_teto_de_20_eventos(self, diacon):
        # limit=20 enchia com cultos e a agenda acabava em 24/09: o Cursilho
        # Masculino (29/10) não existia pra LidIA e caía no RAG velho.
        hoje = datetime.now(_SP).date()
        diacon.return_value = {"events": [
            _ev("Cursilho Masculino", hoje + timedelta(days=46), slug="cursilho-masculino-10-29"),
        ]}

        result = await be.execute({"nome_evento": "Cursilho Masculino"}, "5581", AsyncMock())

        kw = diacon.await_args.kwargs
        assert kw["date_from"] == hoje
        assert kw["date_to"] == hoje + timedelta(days=90)
        assert kw["limit"] >= 200
        assert "Cursilho Masculino" in result
        assert "https://diacon.ia.br/e/cursilho-masculino-10-29" in result

    @pytest.mark.asyncio
    async def test_periodo_pedido_vai_para_a_diacon(self, diacon):
        await be.execute({"data_inicio": "2026-11-01", "data_fim": "2026-11-30"}, "5581", AsyncMock())

        kw = diacon.await_args.kwargs
        assert kw["date_from"] == date(2026, 11, 1)
        assert kw["date_to"] == date(2026, 11, 30)


class TestInscricao:
    @pytest.mark.asyncio
    async def test_diferencia_evento_com_e_sem_inscricao(self, diacon):
        # 13/09: duas "Imersão" nos mesmos dias; só a de Oração tem inscrição.
        dia = datetime.now(_SP).date() + timedelta(days=5)
        diacon.return_value = {"events": [
            _ev("Imersão Céus Abertos", dia, reg=False, slug="imersao-ceus-abertos-09-18", type_="Conferência"),
            _ev("Imersão de Oração - Frutificando no Secreto", dia, reg=True, slug="imersao-ceus-abertos"),
        ]}

        result = await be.execute({"nome_evento": "imersão"}, "5581", AsyncMock())

        blocos = result.split("\n\n")
        ceus = next(b for b in blocos if "Imersão Céus Abertos" in b)
        oracao = next(b for b in blocos if "Imersão de Oração" in b)
        assert "Inscrição: aberta" in oracao
        assert "Inscrição: não tem" in ceus


class TestFallbackSemLinkVelho:
    @pytest.mark.asyncio
    async def test_fallback_rag_nao_devolve_link_de_evento(self, diacon):
        # 11/09: buscar_evento sem achar na Diacon devolveu o link da
        # Conferência 30 Anos (encerrada) vindo da planilha.
        chunk = RAGChunk(
            content=(
                "Pergunta: Quando é a Conferência PAES 30 Anos?\nResposta: acontece de 19 a 22 "
                "de agosto. As inscrições já estão abertas: https://diacon.ia.br/e/conf-30-anos-paes-08-20"
            ),
            source="sheets_informacoes", score=0.69,
        )
        with patch.object(be, "RAGService") as MockRAG:
            MockRAG.return_value.search = AsyncMock(return_value=[chunk])
            MockRAG.return_value.format_chunks = RAGService.__new__(RAGService).format_chunks

            result = await be.execute({"nome_evento": "Conferência 30 anos"}, "5581", AsyncMock())

        assert "diacon.ia.br/e/" not in result
        assert "Conferência PAES 30 Anos" in result

    @pytest.mark.asyncio
    async def test_sem_nada_em_lugar_nenhum(self, diacon):
        with patch.object(be, "RAGService") as MockRAG:
            MockRAG.return_value.search = AsyncMock(return_value=[])
            result = await be.execute({"nome_evento": "Happening"}, "5581", AsyncMock())
        assert "Nenhum evento encontrado" in result
