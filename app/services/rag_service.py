"""Serviço RAG — busca vetorial na base de conhecimento (pgvector).

Responsável por:
- search(): busca semântica por similaridade cosseno
- retrieve_hint(): pré-busca equivalente ao PAES_informacoes do n8n
"""
from __future__ import annotations

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
        """Gera embedding com text-embedding-3-small."""
        resp = await self._oai.embeddings.create(
            model=settings.openai_embedding_model,
            input=text_input,
        )
        return resp.data[0].embedding

    async def search(
        self,
        query: str,
        db: AsyncSession,
        *,
        top_k: int | None = None,
    ) -> list[RAGChunk]:
        """Busca semântica nos knowledge_chunks.

        Retorna os top_k chunks mais relevantes ordenados por similaridade.
        """
        k = top_k or settings.rag_top_k
        if not settings.rag_enabled:
            return []

        try:
            embedding = await self._embed(query)
        except Exception:
            logger.exception("Erro ao gerar embedding para RAG search")
            return []

        # Busca por similaridade cosseno (1 - distance = score)
        sql = text("""
            SELECT content, source, metadata,
                   1 - (embedding <=> :embedding::vector) AS score
            FROM knowledge_chunks
            ORDER BY embedding <=> :embedding::vector
            LIMIT :limit
        """)

        try:
            result = await db.execute(
                sql,
                {"embedding": str(embedding), "limit": k},
            )
            rows = result.fetchall()
        except Exception:
            logger.exception("Erro na busca RAG pgvector")
            return []

        chunks = []
        for row in rows:
            chunks.append(RAGChunk(
                content=row.content,
                source=row.source,
                score=float(row.score) if row.score else 0.0,
            ))

        logger.debug(f"RAG search '{query[:50]}...' → {len(chunks)} chunks (top score: {chunks[0].score:.3f})" if chunks else f"RAG search '{query[:50]}...' → 0 chunks")
        return chunks

    def format_chunks(self, chunks: list[RAGChunk]) -> str:
        """Formata chunks para injeção no contexto."""
        if not chunks:
            return "Sem dica de resposta"
        parts = []
        for i, c in enumerate(chunks, 1):
            src = f" (fonte: {c.source})" if c.source else ""
            parts.append(f"[{i}]{src} {c.content}")
        return "\n\n".join(parts)

    async def retrieve_hint(
        self,
        user_text: str,
        db: AsyncSession,
    ) -> str:
        """Pré-busca RAG equivalente ao PAES_informacoes do n8n.

        Retorna string formatada com chunks ou "Sem dica de resposta".
        """
        if not settings.rag_enabled:
            return "Sem dica de resposta"

        chunks = await self.search(user_text, db, top_k=settings.rag_top_k)
        return self.format_chunks(chunks)
