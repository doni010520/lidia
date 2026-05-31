"""Tool: buscar_documentos — RAG na base vetorial."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.rag_service import RAGService


async def execute(
    args: dict,
    phone: str,
    db: AsyncSession,
) -> str:
    """Busca documentos na base de conhecimento."""
    query = args.get("query", "")
    if not query:
        return "Erro: parâmetro 'query' é obrigatório."

    rag = RAGService()
    chunks = await rag.search(query, db, top_k=settings.rag_top_k)
    return rag.format_chunks(chunks)
