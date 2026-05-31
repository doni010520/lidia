"""Migração de dados do Supabase (n8n) → PostgreSQL local (LidIA).

Tabelas migradas:
  - paes_contacts → contacts
  - novos_convertidos → novos_convertidos
  - eventos_paes → eventos_paes
  - plano_de_leitura → plano_de_leitura

NÃO migrados:
  - documents_paes / knowledge_chunks (re-vectorizado via index_knowledge.py)
  - Histórico de chat (a menos que --include-history)

Uso:
    # Dry run (mostra contagens sem inserir)
    python -m scripts.migrate_from_supabase --dry-run

    # Migração real
    python -m scripts.migrate_from_supabase

    # Com histórico de chat
    python -m scripts.migrate_from_supabase --include-history

Requer:
    SUPABASE_URL=https://xxxx.supabase.co
    SUPABASE_KEY=eyJ...
"""
from __future__ import annotations

import argparse
import asyncio
import os
from datetime import date

import httpx
from loguru import logger
from sqlalchemy import text

from app.db import engine

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")


def _headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


async def _fetch_table(table: str, *, select: str = "*", limit: int = 10000) -> list[dict]:
    """Fetch all rows from a Supabase table via REST API."""
    url = f"{SUPABASE_URL}/rest/v1/{table}?select={select}&limit={limit}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, headers=_headers())
        resp.raise_for_status()
        return resp.json()


def _parse_date_safe(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except (ValueError, IndexError):
        return None


async def migrate_contacts(dry_run: bool = False) -> int:
    """paes_contacts → contacts."""
    rows = await _fetch_table("paes_contacts")
    logger.info(f"Supabase paes_contacts: {len(rows)} registros")

    if dry_run:
        return len(rows)

    async with engine.begin() as conn:
        for row in rows:
            telefone = row.get("telefone", "")
            if not telefone:
                continue
            await conn.execute(
                text("""
                    INSERT INTO contacts (telefone, nome, full_name, email, status, aniversario, cadastro_completo)
                    VALUES (:telefone, :nome, :full_name, :email, :status, :aniversario, TRUE)
                    ON CONFLICT (telefone) DO UPDATE SET
                        nome = COALESCE(EXCLUDED.nome, contacts.nome),
                        full_name = COALESCE(EXCLUDED.full_name, contacts.full_name),
                        email = COALESCE(EXCLUDED.email, contacts.email),
                        status = COALESCE(EXCLUDED.status, contacts.status),
                        aniversario = COALESCE(EXCLUDED.aniversario, contacts.aniversario),
                        cadastro_completo = TRUE
                """),
                {
                    "telefone": telefone,
                    "nome": row.get("nome") or row.get("first_name"),
                    "full_name": row.get("full_name") or row.get("nome"),
                    "email": row.get("email"),
                    "status": row.get("status"),
                    "aniversario": _parse_date_safe(row.get("aniversario")),
                },
            )
    logger.info(f"✅ {len(rows)} contatos migrados")
    return len(rows)


async def migrate_novos_convertidos(dry_run: bool = False) -> int:
    """novos_convertidos → novos_convertidos."""
    rows = await _fetch_table("novos_convertidos")
    logger.info(f"Supabase novos_convertidos: {len(rows)} registros")

    if dry_run:
        return len(rows)

    async with engine.begin() as conn:
        for row in rows:
            telefone = row.get("telefone", "")
            if not telefone:
                continue
            await conn.execute(
                text("""
                    INSERT INTO novos_convertidos (telefone, nome)
                    VALUES (:telefone, :nome)
                    ON CONFLICT (telefone) DO NOTHING
                """),
                {"telefone": telefone, "nome": row.get("nome", "")},
            )
    logger.info(f"✅ {len(rows)} novos convertidos migrados")
    return len(rows)


async def migrate_eventos(dry_run: bool = False) -> int:
    """eventos_paes → eventos_paes."""
    rows = await _fetch_table("eventos_paes")
    logger.info(f"Supabase eventos_paes: {len(rows)} registros")

    if dry_run:
        return len(rows)

    async with engine.begin() as conn:
        for i, row in enumerate(rows):
            nome = row.get("nome", row.get("Nome", ""))
            if not nome:
                continue
            row_id = f"supabase:{i}:{nome[:30].lower()}"
            await conn.execute(
                text("""
                    INSERT INTO eventos_paes
                        (nome, descricao, local, data_inicio, data_final, hora, valor, link, media, sheets_row_id)
                    VALUES
                        (:nome, :descricao, :local, :data_inicio, :data_final, :hora, :valor, :link, :media, :row_id)
                    ON CONFLICT (sheets_row_id) DO UPDATE SET
                        nome = EXCLUDED.nome,
                        descricao = EXCLUDED.descricao,
                        local = EXCLUDED.local,
                        data_inicio = EXCLUDED.data_inicio,
                        data_final = EXCLUDED.data_final
                """),
                {
                    "nome": nome,
                    "descricao": row.get("descricao", ""),
                    "local": row.get("local", ""),
                    "data_inicio": _parse_date_safe(row.get("data_inicio")),
                    "data_final": _parse_date_safe(row.get("data_final")),
                    "hora": row.get("hora"),
                    "valor": row.get("valor", ""),
                    "link": row.get("link", ""),
                    "media": row.get("media", ""),
                    "row_id": row_id,
                },
            )
    logger.info(f"✅ {len(rows)} eventos migrados")
    return len(rows)


async def migrate_plano_leitura(dry_run: bool = False) -> int:
    """plano_de_leitura → plano_de_leitura."""
    rows = await _fetch_table("plano_de_leitura")
    logger.info(f"Supabase plano_de_leitura: {len(rows)} registros")

    if dry_run:
        return len(rows)

    async with engine.begin() as conn:
        for row in rows:
            data = _parse_date_safe(row.get("data"))
            if not data:
                continue
            await conn.execute(
                text("""
                    INSERT INTO plano_de_leitura (data, leitura, capitulos, semana, livro)
                    VALUES (:data, :leitura, :capitulos, :semana, :livro)
                    ON CONFLICT (data) DO UPDATE SET
                        leitura = EXCLUDED.leitura,
                        capitulos = EXCLUDED.capitulos,
                        semana = EXCLUDED.semana,
                        livro = EXCLUDED.livro
                """),
                {
                    "data": data,
                    "leitura": row.get("leitura", ""),
                    "capitulos": row.get("capitulos", ""),
                    "semana": row.get("semana"),
                    "livro": row.get("livro", ""),
                },
            )
    logger.info(f"✅ {len(rows)} leituras migradas")
    return len(rows)


async def migrate_history(dry_run: bool = False) -> int:
    """Migra histórico de chat (opcional)."""
    try:
        rows = await _fetch_table("chat_history", limit=50000)
    except Exception:
        logger.warning("Tabela chat_history não encontrada no Supabase")
        return 0

    logger.info(f"Supabase chat_history: {len(rows)} registros")

    if dry_run:
        return len(rows)

    async with engine.begin() as conn:
        for row in rows:
            phone = row.get("phone", row.get("session_id", ""))
            if not phone:
                continue
            await conn.execute(
                text("""
                    INSERT INTO messages (phone, role, content, created_at)
                    VALUES (:phone, :role, :content, :created_at)
                """),
                {
                    "phone": phone,
                    "role": row.get("role", "user"),
                    "content": row.get("content", row.get("message", "")),
                    "created_at": row.get("created_at"),
                },
            )
    logger.info(f"✅ {len(rows)} mensagens de histórico migradas")
    return len(rows)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Migrar dados do Supabase → PostgreSQL local")
    parser.add_argument("--dry-run", action="store_true", help="Apenas contar, sem inserir")
    parser.add_argument("--include-history", action="store_true", help="Migrar histórico de chat")
    args = parser.parse_args()

    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.error("SUPABASE_URL e SUPABASE_KEY devem estar definidos no .env ou ambiente")
        return

    logger.info(f"Conectando a {SUPABASE_URL}...")
    mode = "DRY RUN" if args.dry_run else "MIGRAÇÃO REAL"
    logger.info(f"=== Modo: {mode} ===")

    results = {
        "contacts": await migrate_contacts(args.dry_run),
        "novos_convertidos": await migrate_novos_convertidos(args.dry_run),
        "eventos": await migrate_eventos(args.dry_run),
        "plano_leitura": await migrate_plano_leitura(args.dry_run),
    }

    if args.include_history:
        results["history"] = await migrate_history(args.dry_run)

    logger.info(f"\n{'='*50}")
    logger.info(f"Resultado da migração ({mode}):")
    for table, count in results.items():
        logger.info(f"  {table}: {count} registros")
    logger.info(f"{'='*50}")

    if not args.dry_run:
        logger.info("\nPróximo passo: re-vectorizar base de conhecimento:")
        logger.info("  python -m scripts.index_knowledge --path ./docs/ --clear")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
