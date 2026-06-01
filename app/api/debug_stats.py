"""Endpoint TEMPORÁRIO de debug — conta linhas e mostra mensagens recentes.
Usado para validar smoke test do webhook. Remove após validação."""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from app.db import async_session_factory

router = APIRouter(prefix="/debug", tags=["debug"])


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
async def recent_messages(token: str = Query(...), limit: int = Query(20)):
    _check(token)
    async with async_session_factory() as db:
        r = await db.execute(text(
            "SELECT phone, role, LEFT(content, 120) AS preview, created_at "
            "FROM messages ORDER BY created_at DESC LIMIT :n"
        ), {"n": limit})
        rows = [dict(row._mapping) for row in r.all()]
    for row in rows:
        if row.get("created_at"):
            row["created_at"] = row["created_at"].isoformat()
    return {"count": len(rows), "rows": rows}
