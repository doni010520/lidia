"""Endpoint TEMPORÁRIO de debug — contagens, mensagens recentes e logs.
Remove após smoke test."""
from __future__ import annotations

import os
from collections import deque
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from loguru import logger
from sqlalchemy import text

from app.db import async_session_factory

router = APIRouter(prefix="/debug", tags=["debug"])

# Ring buffer de logs warning/error/exception (50 mais recentes)
_LOG_BUFFER: deque[dict] = deque(maxlen=100)


def _log_sink(message) -> None:
    """Sink customizado do loguru pra capturar mensagens em memória."""
    rec = message.record
    _LOG_BUFFER.append({
        "ts": rec["time"].isoformat() if hasattr(rec["time"], "isoformat") else str(rec["time"]),
        "level": rec["level"].name,
        "name": rec["name"],
        "function": rec.get("function"),
        "line": rec.get("line"),
        "message": rec["message"][:1500],
        "extra": {k: str(v)[:200] for k, v in rec.get("extra", {}).items()},
        "exception": str(rec.get("exception")) if rec.get("exception") else None,
    })


# Instalar sink na importação do módulo
try:
    logger.add(_log_sink, level="WARNING", format="{message}")
except Exception:
    pass


def _check(token: str) -> None:
    expected = os.getenv("DEBUG_TOKEN", "")
    if not expected or token != expected:
        raise HTTPException(status_code=401, detail="invalid token")


@router.get("/stats")
async def stats(token: str = Query(...)):
    _check(token)
    out = {}
    async with async_session_factory() as db:
        for t in ["contacts", "messages", "eventos_paes", "knowledge_chunks",
                  "liderancas", "pastores_aniversario", "paes_atendimentos_log",
                  "llm_analytics", "plano_de_leitura"]:
            try:
                r = await db.execute(text(f"SELECT COUNT(*) FROM {t}"))
                out[t] = r.scalar()
            except Exception as e:
                out[t] = f"err: {e}"
    return out


@router.get("/recent-messages")
async def recent_messages(token: str = Query(...), limit: int = Query(20), phone: str = Query("")):
    _check(token)
    async with async_session_factory() as db:
        if phone:
            r = await db.execute(text(
                "SELECT phone, role, LEFT(content, 200) AS preview, created_at "
                "FROM messages WHERE phone = :p ORDER BY created_at DESC LIMIT :n"
            ), {"p": phone, "n": limit})
        else:
            r = await db.execute(text(
                "SELECT phone, role, LEFT(content, 200) AS preview, created_at "
                "FROM messages ORDER BY created_at DESC LIMIT :n"
            ), {"n": limit})
        rows = [dict(row._mapping) for row in r.all()]
    for row in rows:
        if row.get("created_at"):
            row["created_at"] = row["created_at"].isoformat()
    return {"count": len(rows), "rows": rows}


@router.get("/logs")
async def logs(token: str = Query(...), level: str = Query("")):
    _check(token)
    items = list(_LOG_BUFFER)
    if level:
        items = [i for i in items if i["level"] == level.upper()]
    return {"count": len(items), "items": items}
