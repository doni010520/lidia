"""Endpoints de debug — testes temporários.
Remove após bateria de testes."""
from __future__ import annotations

import os
from collections import deque

from fastapi import APIRouter, HTTPException, Query
from loguru import logger
from sqlalchemy import text

from app.db import async_session_factory

router = APIRouter(prefix="/debug", tags=["debug"])

_LOG_BUFFER: deque[dict] = deque(maxlen=300)


def _log_sink(message) -> None:
    rec = message.record
    _LOG_BUFFER.append({
        "ts": rec["time"].isoformat() if hasattr(rec["time"], "isoformat") else str(rec["time"]),
        "level": rec["level"].name,
        "name": rec["name"],
        "function": rec.get("function"),
        "line": rec.get("line"),
        "message": rec["message"][:2000],
        "extra": {k: str(v)[:200] for k, v in rec.get("extra", {}).items()},
        "exception": str(rec.get("exception"))[:1500] if rec.get("exception") else None,
    })


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
                  "llm_analytics", "plano_de_leitura", "novos_convertidos",
                  "disparos", "disparo_log"]:
            try:
                r = await db.execute(text(f"SELECT COUNT(*) FROM {t}"))
                out[t] = r.scalar()
            except Exception as e:
                out[t] = f"err: {str(e)[:80]}"
    return out


@router.get("/recent-messages")
async def recent_messages(token: str = Query(...), limit: int = Query(30), phone: str = Query("")):
    _check(token)
    async with async_session_factory() as db:
        if phone:
            r = await db.execute(text(
                "SELECT phone, role, content, tool_name, tool_call_id, tool_calls_json, created_at "
                "FROM messages WHERE phone = :p ORDER BY created_at DESC LIMIT :n"
            ), {"p": phone, "n": limit})
        else:
            r = await db.execute(text(
                "SELECT phone, role, content, tool_name, tool_call_id, tool_calls_json, created_at "
                "FROM messages ORDER BY created_at DESC LIMIT :n"
            ), {"n": limit})
        rows = [dict(row._mapping) for row in r.all()]
    for row in rows:
        if row.get("created_at"):
            row["created_at"] = row["created_at"].isoformat()
    return {"count": len(rows), "rows": rows}


@router.get("/contact")
async def contact_info(token: str = Query(...), phone: str = Query(...)):
    _check(token)
    async with async_session_factory() as db:
        r = await db.execute(text(
            "SELECT * FROM contacts WHERE telefone = :p"
        ), {"p": phone})
        row = r.first()
    if not row:
        return {"found": False}
    d = dict(row._mapping)
    for k, v in d.items():
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat()
    return {"found": True, "contact": d}


@router.get("/history-debug")
async def history_debug(token: str = Query(...), phone: str = Query(...), limit: int = Query(50)):
    """Mostra história crua + identifica problemas (tool órfão, etc)."""
    _check(token)
    from app.services.conversation_service import load_history
    async with async_session_factory() as db:
        history = await load_history(db, phone, limit=limit)
    issues = []
    for i, e in enumerate(history):
        role = e.get("role")
        if role == "tool" and (i == 0 or "tool_calls" not in history[i-1]):
            issues.append({"index": i, "issue": "tool sem tool_calls precedente", "entry": e})
        if role == "assistant" and not e.get("content") and not e.get("tool_calls"):
            issues.append({"index": i, "issue": "assistant vazio sem tool_calls", "entry": {"role": role, "content_len": 0}})
    return {
        "history_length": len(history),
        "issues": issues,
        "snippet": [{"i": i, "role": e.get("role"), "content_len": len(e.get("content") or ""),
                     "has_tool_calls": "tool_calls" in e, "tool_call_id": e.get("tool_call_id"),
                     "name": e.get("name")}
                    for i, e in enumerate(history)],
    }


@router.post("/test-tool")
async def test_tool(token: str = Query(...), name: str = Query(...),
                    phone: str = Query("557193061031"), args: str = Query("{}")):
    """Invoca uma tool diretamente sem passar pelo LLM/webhook.
    args: JSON string com os argumentos.
    Retorna o resultado da tool + qualquer exceção capturada."""
    _check(token)
    import json as _json
    import traceback
    try:
        parsed_args = _json.loads(args) if isinstance(args, str) else (args or {})
    except Exception as e:
        return {"ok": False, "error": f"args inválido: {e}"}

    from app.tools.handlers import handle_tool_call
    async with async_session_factory() as db:
        try:
            result = await handle_tool_call(name, parsed_args, phone, db=db)
            # Emular o commit que normalmente ocorre no pipeline (step 13)
            try:
                await db.commit()
            except Exception:
                pass
            return {"ok": True, "result": result if isinstance(result, str) else str(result)[:2000]}
        except Exception as e:
            return {
                "ok": False,
                "error": f"{type(e).__name__}: {str(e)[:300]}",
                "traceback": traceback.format_exc()[:2500],
            }


@router.post("/migrate-diacon")
async def trigger_diacon_migration(token: str = Query(...), dry_run: bool = Query(True)):
    """Dispara migrate_contacts_to_diacon via subprocess (temporário)."""
    _check(token)
    import asyncio
    import sys
    args = ["-u", "-m", "scripts.migrate_contacts_to_diacon"]
    if dry_run:
        args.append("--dry-run")
    proc = await asyncio.create_subprocess_exec(
        sys.executable, *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd="/app",
    )
    stdout, _ = await proc.communicate()
    output = stdout.decode("utf-8", errors="replace")
    return {
        "return_code": proc.returncode,
        "output_tail": output[-5000:],
    }


@router.get("/sql")
async def debug_sql(token: str = Query(...), q: str = Query(...)):
    """Executa SELECT/COUNT temporário. Bloqueia DDL/DML por segurança."""
    _check(token)
    qlow = q.strip().lower()
    if not (qlow.startswith("select") or qlow.startswith("with")):
        return {"error": "apenas SELECT/WITH permitido"}
    async with async_session_factory() as db:
        try:
            r = await db.execute(text(q))
            rows = [dict(row._mapping) for row in r.fetchall()][:200]
            for row in rows:
                for k, v in row.items():
                    if hasattr(v, "isoformat"):
                        row[k] = v.isoformat()
            return {"count": len(rows), "rows": rows}
        except Exception as e:
            return {"error": f"{type(e).__name__}: {str(e)[:300]}"}


@router.post("/trigger-worker")
async def trigger_worker(token: str = Query(...), worker: str = Query(...)):
    """Dispara um worker manualmente. Workers: aniversarios, boas_vindas."""
    _check(token)
    try:
        if worker == "aniversarios":
            from app.workers.aniversarios import check_aniversariantes
            result = await check_aniversariantes()
        elif worker == "boas_vindas":
            from app.workers.boas_vindas_convertidos import disparar_boas_vindas
            result = await disparar_boas_vindas()
        else:
            return {"ok": False, "error": f"Worker desconhecido: {worker}"}
        return {"ok": True, "result": result}
    except Exception as e:
        import traceback
        return {"ok": False, "error": str(e), "traceback": traceback.format_exc()[:2500]}


@router.post("/delete-knowledge")
async def delete_knowledge(token: str = Query(...), ids: str = Query(...)):
    """Deleta chunks de knowledge_chunks por lista de IDs (CSV). Temporário."""
    _check(token)
    try:
        id_list = [int(x) for x in ids.split(",") if x.strip()]
    except ValueError:
        return {"ok": False, "error": "ids inválido, use CSV de inteiros"}
    if not id_list:
        return {"ok": False, "error": "nenhum id informado"}
    async with async_session_factory() as db:
        try:
            r = await db.execute(
                text("DELETE FROM knowledge_chunks WHERE id = ANY(:ids)"),
                {"ids": id_list},
            )
            await db.commit()
            return {"ok": True, "deleted": r.rowcount, "ids": id_list}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:300]}"}


@router.post("/set-team-phones")
async def set_team_phones(token: str = Query(...), equipe: str = Query(...), phones: str = Query(...)):
    """Define telefones_responsaveis de uma equipe (CSV). Temporário."""
    _check(token)
    phone_list = [p.strip() for p in phones.split(",") if p.strip()]
    async with async_session_factory() as db:
        try:
            r = await db.execute(
                text(
                    "UPDATE equipes_responsaveis SET telefones_responsaveis = :ph "
                    "WHERE equipe ILIKE :eq RETURNING equipe, telefones_responsaveis"
                ),
                {"ph": phone_list, "eq": f"%{equipe}%"},
            )
            rows = [dict(row._mapping) for row in r.fetchall()]
            await db.commit()
            return {"ok": True, "updated": rows}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:300]}"}


@router.get("/logs")
async def logs(token: str = Query(...), level: str = Query(""), grep: str = Query(""), limit: int = Query(200)):
    _check(token)
    items = list(_LOG_BUFFER)
    if level:
        items = [i for i in items if i["level"] == level.upper()]
    if grep:
        g = grep.lower()
        items = [i for i in items if g in (i.get("message") or "").lower()]
    return {"count": len(items), "items": items[-limit:]}
