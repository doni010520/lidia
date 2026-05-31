"""Tool: informacoes_Lidia — ADMIN: CRUD na base de conhecimento."""
from __future__ import annotations

import json

import openai
from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings


async def execute(
    args: dict,
    phone: str,
    db: AsyncSession,
) -> str:
    funcao = args.get("funcao", "")
    pergunta = args.get("Pergunta", args.get("pergunta", ""))
    resposta = args.get("Resposta", args.get("resposta", ""))

    if funcao not in ("cadastrar", "atualizar", "deletar"):
        return "Erro: 'funcao' deve ser 'cadastrar', 'atualizar' ou 'deletar'."

    if funcao == "deletar":
        result = await db.execute(
            text("DELETE FROM knowledge_chunks WHERE content ILIKE :q AND source = 'informacoes_lidia'"),
            {"q": f"%{pergunta}%"},
        )
        await db.commit()
        return f"Removidos {result.rowcount} chunks contendo '{pergunta}'."

    if not pergunta or not resposta:
        return "Erro: 'Pergunta' e 'Resposta' são obrigatórios para cadastrar/atualizar."

    content = f"Pergunta: {pergunta}\nResposta: {resposta}"

    # Vectorizar
    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
    try:
        emb_resp = await client.embeddings.create(
            model=settings.openai_embedding_model,
            input=content,
        )
        embedding = emb_resp.data[0].embedding
    except Exception:
        logger.exception("Erro ao gerar embedding para informação")
        return "Erro ao vectorizar a informação."

    # Deletar anterior (se atualizar)
    if funcao == "atualizar":
        await db.execute(
            text("DELETE FROM knowledge_chunks WHERE content ILIKE :q AND source = 'informacoes_lidia'"),
            {"q": f"%{pergunta}%"},
        )

    # Inserir
    await db.execute(
        text("""
            INSERT INTO knowledge_chunks (content, embedding, metadata, source)
            VALUES (:content, :embedding::vector, :metadata::jsonb, 'informacoes_lidia')
        """),
        {
            "content": content,
            "embedding": str(embedding),
            "metadata": json.dumps({"source": "informacoes_lidia", "pergunta": pergunta}),
        },
    )
    await db.commit()
    logger.info(f"Informação {funcao}: {pergunta[:50]}...")
    return f"Informação '{pergunta}' {funcao} com sucesso na base de conhecimento."
