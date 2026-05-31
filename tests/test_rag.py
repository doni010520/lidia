"""Testes para o RAGService — formatação de chunks e retrieve_hint."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.rag_service import RAGChunk, RAGService


class TestFormatChunks:
    def test_empty_chunks(self):
        svc = RAGService.__new__(RAGService)
        result = svc.format_chunks([])
        assert result == "Sem dica de resposta"

    def test_single_chunk(self):
        svc = RAGService.__new__(RAGService)
        chunks = [RAGChunk(content="A PAES fica na Rua da Aurora", source="info.pdf", score=0.92)]
        result = svc.format_chunks(chunks)
        assert "[1]" in result
        assert "info.pdf" in result
        assert "A PAES fica na Rua da Aurora" in result

    def test_multiple_chunks(self):
        svc = RAGService.__new__(RAGService)
        chunks = [
            RAGChunk(content="Culto domingo 10h", source="eventos.pdf", score=0.95),
            RAGChunk(content="Célula quarta 19h", source="celulas.pdf", score=0.88),
            RAGChunk(content="Dízimo via PIX", source="financeiro.pdf", score=0.75),
        ]
        result = svc.format_chunks(chunks)
        assert "[1]" in result
        assert "[2]" in result
        assert "[3]" in result
        assert "eventos.pdf" in result
        assert "Culto domingo 10h" in result

    def test_chunk_without_source(self):
        svc = RAGService.__new__(RAGService)
        chunks = [RAGChunk(content="Conteúdo sem fonte", source=None, score=0.80)]
        result = svc.format_chunks(chunks)
        assert "[1]" in result
        assert "(fonte:" not in result
        assert "Conteúdo sem fonte" in result


class TestRetrieveHint:
    @pytest.mark.asyncio
    async def test_rag_disabled_returns_sem_dica(self, monkeypatch):
        monkeypatch.setattr("app.services.rag_service.settings", MagicMock(
            rag_enabled=False,
            openai_api_key="sk-test",
            openai_embedding_model="text-embedding-3-small",
            rag_top_k=7,
        ))
        svc = RAGService.__new__(RAGService)
        result = await svc.retrieve_hint("qualquer texto", AsyncMock())
        assert result == "Sem dica de resposta"

    @pytest.mark.asyncio
    async def test_retrieve_hint_with_results(self, monkeypatch):
        monkeypatch.setattr("app.services.rag_service.settings", MagicMock(
            rag_enabled=True,
            openai_api_key="sk-test",
            openai_embedding_model="text-embedding-3-small",
            rag_top_k=3,
        ))

        svc = RAGService.__new__(RAGService)
        # Mock search para retornar chunks
        svc.search = AsyncMock(return_value=[
            RAGChunk(content="Culto domingo 10h", source="eventos.pdf", score=0.95),
            RAGChunk(content="Célula quarta 19h", source="celulas.pdf", score=0.88),
        ])

        db = AsyncMock()
        result = await svc.retrieve_hint("quando é o culto?", db)

        assert "Culto domingo 10h" in result
        assert "Célula quarta 19h" in result
        svc.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_retrieve_hint_empty_results(self, monkeypatch):
        monkeypatch.setattr("app.services.rag_service.settings", MagicMock(
            rag_enabled=True,
            openai_api_key="sk-test",
            openai_embedding_model="text-embedding-3-small",
            rag_top_k=3,
        ))

        svc = RAGService.__new__(RAGService)
        svc.search = AsyncMock(return_value=[])

        result = await svc.retrieve_hint("algo obscuro", AsyncMock())
        assert result == "Sem dica de resposta"


class TestChunkScoring:
    def test_chunks_preserve_order(self):
        """Chunks devem manter a ordem (por score, como retornado pela query)."""
        svc = RAGService.__new__(RAGService)
        chunks = [
            RAGChunk(content="Primeiro", source="a.pdf", score=0.99),
            RAGChunk(content="Segundo", source="b.pdf", score=0.85),
            RAGChunk(content="Terceiro", source="c.pdf", score=0.70),
        ]
        result = svc.format_chunks(chunks)
        idx_first = result.index("Primeiro")
        idx_second = result.index("Segundo")
        idx_third = result.index("Terceiro")
        assert idx_first < idx_second < idx_third
