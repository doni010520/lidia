"""Sobe todos os contatos do Postgres para a Diacon via POST /members.

Idempotente: POST /members faz dedup por telefone (retorna created=False
se já existe). Roda em batches respeitando 180 req/min.

Uso:
    python -m scripts.migrate_contacts_to_diacon --dry-run
    python -m scripts.migrate_contacts_to_diacon
"""
from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from datetime import date

from loguru import logger
from sqlalchemy import select

from app.db import async_session_factory
from app.models.conversation import Contact
from app.services import diacon_client


def _map_status(s: str | None) -> str:
    s = (s or "").lower().strip()
    if s in ("membro", "active", "member"):
        return "active"
    if s in ("visitante", "visitor"):
        return "visitor"
    if s in ("inativo", "inactive"):
        return "inactive"
    if s in ("pendente", "pending"):
        return "pending"
    return "active"


async def _migrate(dry: bool) -> dict:
    if not diacon_client.is_enabled():
        logger.error("Diacon não configurado")
        return {}

    async with async_session_factory() as db:
        result = await db.execute(select(Contact).order_by(Contact.id))
        rows = list(result.scalars().all())

    logger.info(f"Total no Postgres: {len(rows)}")

    counts: Counter[str] = Counter()
    errors: list[dict] = []

    for i, c in enumerate(rows, 1):
        full_name = (c.full_name or c.nome or "").strip()
        if not full_name:
            counts["skip_sem_nome"] += 1
            continue

        phone = (c.telefone or "").strip()
        if not phone:
            counts["skip_sem_telefone"] += 1
            continue

        if dry:
            counts["dry_ok"] += 1
            if i <= 5 or i % 100 == 0:
                logger.debug(f"[{i}/{len(rows)}] {phone} → {full_name}")
            continue

        birth_iso = None
        if isinstance(c.aniversario, date):
            birth_iso = c.aniversario.isoformat()

        try:
            resp = await diacon_client.member_create(
                full_name=full_name,
                phone=phone,
                email=c.email or None,
                birth_date=birth_iso,
                status=_map_status(c.status),
                notes="Migrado automaticamente da LidIA.",
            )
            if resp.get("created"):
                counts["created"] += 1
            else:
                counts["already"] += 1
        except diacon_client.DiaconError as e:
            counts[f"err_{e.code or e.status or 'unknown'}"] += 1
            errors.append({
                "phone": phone,
                "name": full_name,
                "status": e.status,
                "code": e.code,
                "msg": str(e)[:200],
            })
            if e.status == 429:
                logger.warning("Rate limit — esperando 30s")
                await asyncio.sleep(30)

        if i % 50 == 0:
            logger.info(
                f"Progresso {i}/{len(rows)} — created={counts['created']} "
                f"already={counts['already']} errors={sum(v for k,v in counts.items() if k.startswith('err_'))}"
            )

        # Respeitar rate-limit: 180 req/min = 3 req/s
        await asyncio.sleep(0.35)

    return {"counts": dict(counts), "errors": errors[:50]}


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    summary = await _migrate(args.dry_run)
    logger.info("===== RESULTADO =====")
    logger.info(json.dumps(summary, indent=2, ensure_ascii=False)[:3000])


if __name__ == "__main__":
    asyncio.run(main())
