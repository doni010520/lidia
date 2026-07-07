"""Servico RAG - busca vetorial com filtro de data (function match_documents)."""
from __future__ import annotations
import json
from dataclasses import dataclass
import openai
from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings


@dataclass
class RAGChunk:
    content: str
    source: str | None
    score: float


class RAGService:
    def __init__(self) -> None:
        self._oai = openai.AsyncOpenAI(api_key=settings.openai_api_key)

    async def _embed(self, text_input: str) -> list[float]:
        resp = await self._oai.embeddings.create(
            model=settings.openai_embedding_model, input=text_input,
        )
        return resp.data[0].embedding

    async def search(
        self, query: str, db: AsyncSession, *,
        top_k: int | None = None, source_filter: str | None = None,
    ) -> list[RAGChunk]:
        """db é mantido na assinatura por compat, mas SEMPRE usamos sessão
        isolada — assim erros do match_documents não envenenam a transação
        principal do process_message."""
        k = top_k or settings.rag_top_k
        if not settings.rag_enabled:
            return []
        try:
            embedding = await self._embed(query)
        except Exception:
            logger.exception("Erro ao gerar embedding")
            return []

        from app.db import async_session_factory

        # Query direta em knowledge_chunks (lidia). NÃO usamos match_documents:
        # existem 2 overloads (lidia + public antiga que lê documents_paes) e,
        # dependendo do search_path da conexão, a chamada resolvia pra função
        # errada — retornando embeddings velhos e ignorando os chunks certos.
        # Sessão isolada: um erro aqui não envenena a transação do process_message.
        async with async_session_factory() as iso_db:
            try:
                return await self._search_fallback(embedding, iso_db, k, source_filter)
            except Exception:
                logger.exception("Erro na busca RAG")
                return []

    async def _search_fallback(self, embedding, db, k, source_filter):
        params = {"embedding": str(embedding), "limit": k}
        where = ""
        if source_filter:
            where = "WHERE source = :src"
            params["src"] = source_filter
        sql = text(f"""
            SELECT content, source,
                   1 - (embedding <=> CAST(:embedding AS vector)) AS score
            FROM knowledge_chunks {where}
            ORDER BY embedding <=> CAST(:embedding AS vector) LIMIT :limit
        """)
        try:
            result = await db.execute(sql, params)
            return [RAGChunk(content=r.content, source=r.source, score=float(r.score) if r.score else 0.0)
                    for r in result.fetchall()]
        except Exception:
            logger.exception("Erro no fallback RAG")
            return []

    def format_chunks(self, chunks: list[RAGChunk]) -> str:
        if not chunks:
            return "Sem dica de resposta"
        parts = []
        for i, c in enumerate(chunks, 1):
            src = f" (fonte: {c.source})" if c.source else ""
            parts.append(f"[{i}]{src} {c.content}")
        return "\n\n".join(parts)

    async def retrieve_hint(self, user_text: str, db: AsyncSession) -> str:
        if not settings.rag_enabled:
            return "Sem dica de resposta"
        chunks = await self.search(user_text, db, top_k=settings.rag_top_k)
        return self.format_chunks(chunks)
