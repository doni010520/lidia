"""Worker: disparo_liderancas - tercas 9h BR (portado de PFvYkIG294XkMkDp)."""
from __future__ import annotations
import asyncio
import openai
from loguru import logger
from sqlalchemy import select
from app.core.config import settings
from app.db import async_session_factory
from app.models.liderancas import Lideranca
from app.services.deps import get_uaz_client

_SYSTEM_PROMPT = """Voce e LidIA, assistente virtual da PAES. Apoia liderancas.
Tom amigavel, prestativo, encorajador. Emojis com moderacao.

Gere mensagem WhatsApp personalizada para o(a) lider:
1. Saudacao calorosa com o nome
2. Apresente-se como LidIA, mencione o ministerio, ofereca ajuda operacional
3. Pergunte se tem novidades para cadastrar (eventos, agenda, materiais)
4. Encerramento curto com bencao

Regras:
- Acolhedor mas profissional
- Maximo 6 linhas
- *negrito* (asterisco simples), NUNCA **
- NAO invente eventos
"""

async def _fetch_liderancas() -> list[dict]:
    async with async_session_factory() as db:
        result = await db.execute(select(Lideranca))
        return [{"id": l.id, "nome": l.nome, "telefone": l.telefone, "ministerio": l.ministerio}
                for l in result.scalars().all() if l.telefone]

async def _gerar_mensagem(nome: str, ministerio: str, client: openai.AsyncOpenAI) -> str:
    resp = await client.chat.completions.create(
        model=settings.openai_model, temperature=0.6, max_tokens=400,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"meu nome: {nome}\nmeu ministerio: {ministerio}"},
        ],
    )
    return (resp.choices[0].message.content or "").strip()

async def disparar_liderancas() -> dict[str, int]:
    lideres = await _fetch_liderancas()
    if not lideres:
        logger.info("Nenhuma lideranca cadastrada.")
        return {"liderancas": 0, "enviadas": 0, "falhas": 0}
    logger.info(f"Disparando para {len(lideres)} lideranca(s).")
    uaz = get_uaz_client()
    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
    enviadas = 0
    falhas = 0
    for lider in lideres:
        try:
            msg = await _gerar_mensagem(lider["nome"] or "lider", lider["ministerio"] or "ministerio", client)
            partes = [p.strip().replace("*", "") for p in msg.split("\n\n") if p.strip()]
            for parte in partes:
                await uaz.send_text(lider["telefone"], parte, delay=3000)
                await asyncio.sleep(3)
            enviadas += 1
        except Exception:
            logger.exception(f"Falha ao disparar para {lider['telefone']}")
            falhas += 1
    return {"liderancas": len(lideres), "enviadas": enviadas, "falhas": falhas}
