"""Link temporário pra arquivo gerado na hora (PDFs da Diacon: QR, resumo,
relatório, material, inscrição).

A uazapi aceitava o arquivo em base64 no JSON; a Zernio só aceita URL. O
arquivo fica 1h no Redis e sai em /m/<token>/<nome>. Token aleatório de 32
bytes: o link não é adivinhável.
"""
from __future__ import annotations

import json
import secrets
from urllib.parse import quote

import redis.asyncio as aioredis

from app.core.config import settings

_TTL = 3600
_BASE = "https://lidia.benitechlab.com"
_redis: aioredis.Redis | None = None


def _r() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url)
    return _redis


async def publicar(content: bytes, mimetype: str, nome: str | None = None) -> str:
    token = secrets.token_urlsafe(32)
    nome = nome or ("arquivo.pdf" if "pdf" in mimetype else "arquivo")
    await _r().set(f"mtemp:{token}", content, ex=_TTL)
    await _r().set(f"mtemp:{token}:meta", json.dumps({"mimetype": mimetype, "nome": nome}), ex=_TTL)
    return f"{_BASE}/m/{token}/{quote(nome)}"


async def obter(token: str) -> tuple[bytes, str, str] | None:
    content = await _r().get(f"mtemp:{token}")
    meta = await _r().get(f"mtemp:{token}:meta")
    if content is None or meta is None:
        return None
    m = json.loads(meta)
    return content, m["mimetype"], m["nome"]
