"""Worker: boas_vindas_convertidos - segundas 10h BR (portado de HAhwOnV1Rj7p62NG)."""
from __future__ import annotations
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
import openai
from loguru import logger
from sqlalchemy import select, delete
from app.core.config import settings
from app.db import async_session_factory
from app.models.novos_convertidos import NovoConvertido
from app.services.deps import get_uaz_client
from app.services import drive_client

_SYSTEM_PROMPT = """Hoje e: {data_atual}
Nome do contato: {nome}

Voce e LidIA, da PAES. Gere mensagem de boas-vindas para quem decidiu por Cristo.

Estrutura:
1. Saudacao com o nome
2. Celebrar a decisao por Cristo
3. Familia PAES
4. Convidar para proximo culto/celula
5. Encerrar com bencao

Regras: tom acolhedor, max 8 linhas, *negrito* (simples). Emojis com moderacao.
"""

async def _fetch_convertidos() -> list[dict]:
    async with async_session_factory() as db:
        result = await db.execute(select(NovoConvertido))
        return [{"id": c.id, "nome": c.nome or "amigo(a)", "telefone": c.telefone}
                for c in result.scalars().all() if c.telefone]

async def _gerar_mensagem(nome: str, client: openai.AsyncOpenAI) -> str:
    data_br = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d de %B de %Y")
    resp = await client.chat.completions.create(
        model=settings.openai_model, temperature=0.7, max_tokens=500,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT.format(data_atual=data_br, nome=nome)},
            {"role": "user", "content": f"Gere a mensagem de boas-vindas para {nome}."},
        ],
    )
    return (resp.choices[0].message.content or "").strip()

async def _remover_convertido(convertido_id: int) -> None:
    async with async_session_factory() as db:
        await db.execute(delete(NovoConvertido).where(NovoConvertido.id == convertido_id))
        await db.commit()

async def disparar_boas_vindas() -> dict[str, int]:
    convertidos = await _fetch_convertidos()
    if not convertidos:
        logger.info("Sem novos convertidos.")
        return {"convertidos": 0, "enviados": 0, "falhas": 0}
    logger.info(f"Boas-vindas para {len(convertidos)} convertido(s).")
    uaz = get_uaz_client()
    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
    video_url = None
    video_file_id = getattr(settings, "drive_video_boas_vindas", "") or ""
    if video_file_id:
        try:
            video_url = drive_client.get_public_url(video_file_id)
        except Exception:
            logger.warning("Falha ao obter URL do video")
    enviados = 0
    falhas = 0
    for c in convertidos:
        try:
            msg = await _gerar_mensagem(c["nome"], client)
            if video_url:
                try:
                    await uaz.send_media(number=c["telefone"], file=video_url, type="video", text=None, delay=3000)
                    await asyncio.sleep(2)
                except Exception:
                    logger.exception(f"Falha ao enviar video para {c['telefone']}")
            partes = [p.strip().replace("*", "") for p in msg.split("\n\n") if p.strip()]
            for parte in partes:
                await uaz.send_text(c["telefone"], parte, delay=3000)
                await asyncio.sleep(3)
            await _remover_convertido(c["id"])
            enviados += 1
        except Exception:
            logger.exception(f"Falha ao processar convertido {c['telefone']}")
            falhas += 1
    return {"convertidos": len(convertidos), "enviados": enviados, "falhas": falhas}
