"""Endpoint TEMPORÁRIO de migração Supabase -> Postgres.

Remove após uso. Protegido por token (env MIGRATE_TOKEN).
Roda o script como subprocess pra não compartilhar engine do app.

POST /admin/migrate?token=...&include_history=true&dry_run=false
GET  /admin/migrate/status?token=...  -> {state, log_tail}
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/admin/migrate", tags=["admin-migrate"])

_STATE: dict = {
    "state": "idle",           # idle | running | done | error
    "started_at": None,
    "finished_at": None,
    "log_lines": [],
    "return_code": None,
}


def _check_token(token: str) -> None:
    expected = os.getenv("MIGRATE_TOKEN", "")
    if not expected or token != expected:
        raise HTTPException(status_code=401, detail="invalid token")


async def _run_subprocess(args: list[str]) -> None:
    _STATE["state"] = "running"
    _STATE["started_at"] = datetime.utcnow().isoformat()
    _STATE["finished_at"] = None
    _STATE["log_lines"] = []
    _STATE["return_code"] = None

    cmd = [sys.executable, "-u", "-m", "scripts.migrate_from_supabase", *args]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd="/app",
        )

        async def reader():
            assert proc.stdout
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                _STATE["log_lines"].append(line.decode("utf-8", errors="replace").rstrip())
                if len(_STATE["log_lines"]) > 2000:
                    _STATE["log_lines"] = _STATE["log_lines"][-2000:]

        await reader()
        _STATE["return_code"] = await proc.wait()
        _STATE["state"] = "done" if _STATE["return_code"] == 0 else "error"
    except Exception as e:
        _STATE["state"] = "error"
        _STATE["log_lines"].append(f"EXCEPTION: {type(e).__name__}: {e}")
    finally:
        _STATE["finished_at"] = datetime.utcnow().isoformat()


@router.post("")
async def trigger_migration(
    token: str = Query(...),
    include_history: bool = Query(False),
    dry_run: bool = Query(True),
):
    _check_token(token)
    if _STATE["state"] == "running":
        raise HTTPException(status_code=409, detail="migration already running")

    args = []
    if dry_run:
        args.append("--dry-run")
    if include_history:
        args.append("--include-history")

    asyncio.create_task(_run_subprocess(args))
    return {"ok": True, "started": True, "dry_run": dry_run, "include_history": include_history}


@router.get("/status")
async def migration_status(token: str = Query(...)):
    _check_token(token)
    return {
        "state": _STATE["state"],
        "started_at": _STATE["started_at"],
        "finished_at": _STATE["finished_at"],
        "return_code": _STATE["return_code"],
        "log_tail": "\n".join(_STATE["log_lines"][-200:]),
        "log_lines_total": len(_STATE["log_lines"]),
    }
