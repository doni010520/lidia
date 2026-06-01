"""Migra dados Supabase legado (n8n) -> Postgres novo (FastAPI).

Tabelas migradas:
  - paes_contacts -> contacts (com mapeamento lidia/ON-OFF -> ai_enabled)
  - novos_convertidos -> novos_convertidos
  - eventos_paes -> eventos_paes (rename de campos: nome_evento->nome, etc)
  - plano_de_leitura -> plano_de_leitura
  - documents_paes + teologia_base -> knowledge_chunks (source diferenciado)
  - liderancas -> liderancas
  - pastores_aniversario -> pastores_aniversario
  - paes_atendimentos_log -> paes_atendimentos_log (trilha auditoria)
  - llm_analytics -> llm_analytics

NAO migrado (decisao operador):
  - contatos_sem_sobrenome (campanha pontual ja encerrada)

Opcional (--include-history):
  - n8n_chat_histories -> messages (formato LangChain -> user/assistant)

Uso:
  python -m scripts.migrate_from_supabase --dry-run
  python -m scripts.migrate_from_supabase
  python -m scripts.migrate_from_supabase --include-history
"""
from __future__ import annotations
import argparse
import asyncio
import json
import os
from datetime import date, datetime
import httpx
from loguru import logger
from sqlalchemy import text
from app.db import engine

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")


def _headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


async def _fetch_paginated(table, page_size=1000):
    """Pagina mesmo se o servidor cortar abaixo do page_size pedido.
    Só para quando o batch vier vazio."""
    rows = []
    offset = 0
    async with httpx.AsyncClient(timeout=120.0) as client:
        while True:
            url = f"{SUPABASE_URL}/rest/v1/{table}?select=*&order=id&limit={page_size}&offset={offset}"
            r = await client.get(url, headers=_headers())
            r.raise_for_status()
            batch = r.json()
            if not batch:
                break
            rows.extend(batch)
            offset += len(batch)
    return rows


def _date(s):
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except Exception:
        return None


def _dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def _int(s):
    if s is None or s == "":
        return None
    try:
        return int(s)
    except Exception:
        return None


# ── SQLs prepared ───────────────────────────────────────────────

_SQL_CONTACTS = text(
    "INSERT INTO contacts (telefone, nome, full_name, email, status, aniversario, "
    "ultimo_contato, ai_enabled, cadastro_completo, pediu_aniversario, follow_up, "
    "etiqueta, ministerio_de_interesse, ministerio_de_servico, created_at) "
    "VALUES (:tel, :n, :fn, :e, :s, :a, :uc, :ae, TRUE, :pa, :fu, :et, :mi, :ms, :ct) "
    "ON CONFLICT (telefone) DO UPDATE SET "
    "nome = COALESCE(EXCLUDED.nome, contacts.nome), "
    "full_name = COALESCE(EXCLUDED.full_name, contacts.full_name), "
    "email = COALESCE(EXCLUDED.email, contacts.email), "
    "status = COALESCE(EXCLUDED.status, contacts.status), "
    "aniversario = COALESCE(EXCLUDED.aniversario, contacts.aniversario), "
    "ultimo_contato = GREATEST(EXCLUDED.ultimo_contato, contacts.ultimo_contato), "
    "ai_enabled = EXCLUDED.ai_enabled, cadastro_completo = TRUE, "
    "pediu_aniversario = COALESCE(EXCLUDED.pediu_aniversario, contacts.pediu_aniversario), "
    "follow_up = COALESCE(EXCLUDED.follow_up, contacts.follow_up), "
    "etiqueta = COALESCE(EXCLUDED.etiqueta, contacts.etiqueta), "
    "ministerio_de_interesse = COALESCE(EXCLUDED.ministerio_de_interesse, contacts.ministerio_de_interesse), "
    "ministerio_de_servico = COALESCE(EXCLUDED.ministerio_de_servico, contacts.ministerio_de_servico)"
)


async def migrate_contacts(dry):
    rows = await _fetch_paginated("paes_contacts")
    logger.info(f"paes_contacts: {len(rows)}")
    if dry:
        return len(rows)
    async with engine.begin() as conn:
        for r in rows:
            tel = (r.get("telefone") or "").strip()
            if not tel:
                continue
            ai_enabled = (r.get("lidia") or "ON").upper() != "OFF"
            await conn.execute(_SQL_CONTACTS, {
                "tel": tel,
                "n": r.get("nome_completo"),
                "fn": r.get("nome_completo"),
                "e": r.get("email"),
                "s": r.get("status"),
                "a": _date(r.get("aniversario")),
                "uc": _dt(r.get("ultimo_contato")),
                "ae": ai_enabled,
                "pa": _dt(r.get("pediu_aniversario")),
                "fu": r.get("follow_up"),
                "et": r.get("etiqueta"),
                "mi": r.get("ministerio_de_interesse"),
                "ms": r.get("ministerio_de_servico"),
                "ct": _dt(r.get("created_at")),
            })
    return len(rows)


async def migrate_novos_convertidos(dry):
    rows = await _fetch_paginated("novos_convertidos")
    logger.info(f"novos_convertidos: {len(rows)}")
    if dry:
        return len(rows)
    sql = text(
        "INSERT INTO novos_convertidos (telefone, nome, created_at) "
        "VALUES (:t, :n, :c) ON CONFLICT (telefone) DO NOTHING"
    )
    async with engine.begin() as conn:
        for r in rows:
            tel = (r.get("telefone") or "").strip()
            if not tel:
                continue
            await conn.execute(sql, {"t": tel, "n": r.get("nome"), "c": _dt(r.get("created_at"))})
    return len(rows)


async def migrate_eventos(dry):
    rows = await _fetch_paginated("eventos_paes")
    logger.info(f"eventos_paes: {len(rows)}")
    if dry:
        return len(rows)
    sql = text(
        "INSERT INTO eventos_paes (nome, descricao, local, data_inicio, data_final, "
        "hora, valor, link, origem, sheets_row_id, created_at) "
        "VALUES (:n, :d, :l, :di, :df, :h, :v, :lk, 'sheets', :ri, :c) "
        "ON CONFLICT (sheets_row_id) DO UPDATE SET "
        "nome = EXCLUDED.nome, descricao = EXCLUDED.descricao, "
        "local = EXCLUDED.local, data_inicio = EXCLUDED.data_inicio, "
        "data_final = EXCLUDED.data_final, hora = EXCLUDED.hora, "
        "valor = EXCLUDED.valor, link = EXCLUDED.link"
    )
    async with engine.begin() as conn:
        for r in rows:
            nome = r.get("nome_evento") or r.get("nome")
            if not nome:
                continue
            await conn.execute(sql, {
                "n": nome,
                "d": r.get("detalhes") or r.get("descricao"),
                "l": r.get("local_evento") or r.get("local"),
                "di": _date(r.get("data_inicio")),
                "df": _date(r.get("data_fim") or r.get("data_final")),
                "h": r.get("hora"),
                "v": r.get("valor"),
                "lk": r.get("link_inscricao") or r.get("link"),
                "ri": f"supabase:evento:{r.get('id')}",
                "c": _dt(r.get("criado_em") or r.get("created_at")),
            })
    return len(rows)


async def migrate_plano_leitura(dry):
    rows = await _fetch_paginated("plano_de_leitura")
    logger.info(f"plano_de_leitura: {len(rows)}")
    if dry:
        return len(rows)
    sql = text(
        "INSERT INTO plano_de_leitura (data, leitura, capitulos, semana, livro) "
        "VALUES (:d, :l, :c, :s, :liv) "
        "ON CONFLICT (data) DO UPDATE SET "
        "leitura = EXCLUDED.leitura, capitulos = EXCLUDED.capitulos, "
        "semana = EXCLUDED.semana, livro = EXCLUDED.livro"
    )
    async with engine.begin() as conn:
        for r in rows:
            d = _date(r.get("data"))
            if not d:
                continue
            await conn.execute(sql, {
                "d": d,
                "l": r.get("leitura") or r.get("titulo"),
                "c": r.get("capitulos"),
                "s": _int(r.get("semana")),
                "liv": r.get("livro") or r.get("dia"),
            })
    return len(rows)


async def migrate_knowledge(dry):
    docs = await _fetch_paginated("documents_paes")
    teo = await _fetch_paginated("teologia_base")
    total = len(docs) + len(teo)
    logger.info(f"documents_paes: {len(docs)} + teologia_base: {len(teo)} = {total}")
    if dry:
        return total
    del_sql = text("DELETE FROM knowledge_chunks WHERE source IN ('documents_paes', 'teologia')")
    ins_doc = text(
        "INSERT INTO knowledge_chunks (content, embedding, metadata, source) "
        "VALUES (:c, CAST(:e AS vector), CAST(:m AS jsonb), 'documents_paes')"
    )
    ins_teo = text(
        "INSERT INTO knowledge_chunks (content, embedding, metadata, source) "
        "VALUES (:c, CAST(:e AS vector), CAST(:m AS jsonb), 'teologia')"
    )
    async with engine.begin() as conn:
        await conn.execute(del_sql)
        for r in docs:
            c = r.get("content")
            if not c:
                continue
            await conn.execute(ins_doc, {
                "c": c,
                "e": str(r.get("embedding") or []),
                "m": json.dumps(r.get("metadata") or {}),
            })
        for r in teo:
            c = r.get("content")
            if not c:
                continue
            await conn.execute(ins_teo, {
                "c": c,
                "e": str(r.get("embedding") or []),
                "m": json.dumps(r.get("metadata") or {}),
            })
    return total


async def migrate_liderancas(dry):
    rows = await _fetch_paginated("liderancas")
    logger.info(f"liderancas: {len(rows)}")
    if dry:
        return len(rows)
    sql = text(
        "INSERT INTO liderancas (nome, telefone, ministerio, created_at) "
        "VALUES (:n, :t, :m, :c)"
    )
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE liderancas RESTART IDENTITY"))
        for r in rows:
            await conn.execute(sql, {
                "n": r.get("nome"),
                "t": r.get("telefone"),
                "m": r.get("ministerio"),
                "c": _dt(r.get("created_at")),
            })
    return len(rows)


async def migrate_pastores(dry):
    rows = await _fetch_paginated("pastores_aniversario")
    logger.info(f"pastores_aniversario: {len(rows)}")
    if dry:
        return len(rows)
    sql = text(
        "INSERT INTO pastores_aniversario (nome, telefone, created_at) "
        "VALUES (:n, :t, :c)"
    )
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE pastores_aniversario RESTART IDENTITY"))
        for r in rows:
            await conn.execute(sql, {
                "n": r.get("nome"),
                "t": r.get("telefone"),
                "c": _dt(r.get("created_at")),
            })
    return len(rows)


async def migrate_atendimentos_log(dry):
    rows = await _fetch_paginated("paes_atendimentos_log")
    logger.info(f"paes_atendimentos_log: {len(rows)}")
    if dry:
        return len(rows)
    sql = text(
        "INSERT INTO paes_atendimentos_log (telefone, nome, status_momento, "
        "ministerio_momento, data_hora, tipo_interacao) "
        "VALUES (:tel, :n, :s, :mm, :dh, :ti)"
    )
    async with engine.begin() as conn:
        for r in rows:
            await conn.execute(sql, {
                "tel": r.get("telefone") or "",
                "n": r.get("nome"),
                "s": r.get("status_momento"),
                "mm": r.get("ministerio_momento"),
                "dh": _dt(r.get("data_hora")),
                "ti": r.get("tipo_interacao"),
            })
    return len(rows)


async def migrate_analytics(dry):
    rows = await _fetch_paginated("llm_analytics")
    logger.info(f"llm_analytics: {len(rows)}")
    if dry:
        return len(rows)
    sql = text(
        "INSERT INTO llm_analytics (session_id, model_name, agent_type, "
        "prompt_tokens, completion_tokens, total_tokens, cost_usd, "
        "intent_detected, sentiment_score, response_time_ms, tools_called, created_at) "
        "VALUES (:s, :m, :a, :pt, :ct, :tt, :cu, :i, :ss, :rt, :tc, :ca)"
    )
    async with engine.begin() as conn:
        for r in rows:
            await conn.execute(sql, {
                "s": r.get("session_id") or "",
                "m": r.get("model_name") or "gpt-4.1-mini",
                "a": r.get("agent_type") or "atendimento",
                "pt": r.get("prompt_tokens"),
                "ct": r.get("completion_tokens"),
                "tt": r.get("total_tokens"),
                "cu": r.get("cost_usd"),
                "i": r.get("intent_detected"),
                "ss": r.get("sentiment_score"),
                "rt": r.get("response_time_ms"),
                "tc": r.get("tools_called") or [],
                "ca": _dt(r.get("created_at")),
            })
    return len(rows)


async def migrate_chat_history(dry):
    rows = await _fetch_paginated("n8n_chat_histories", page_size=5000)
    logger.info(f"n8n_chat_histories: {len(rows)}")
    if dry:
        return len(rows)
    sql = text(
        "INSERT INTO messages (phone, role, content, created_at) "
        "VALUES (:p, :r, :c, NOW())"
    )
    async with engine.begin() as conn:
        for r in rows:
            sid = r.get("session_id") or ""
            msg = r.get("message") or {}
            if isinstance(msg, str):
                try:
                    msg = json.loads(msg)
                except Exception:
                    continue
            mt = msg.get("type")
            if mt == "human":
                role = "user"
            elif mt == "ai":
                role = "assistant"
            else:
                continue
            content = msg.get("content") or ""
            if not content.strip():
                continue
            await conn.execute(sql, {"p": sid, "r": role, "c": content})
    return len(rows)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--include-history", action="store_true")
    args = parser.parse_args()

    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.error("SUPABASE_URL e SUPABASE_KEY obrigatorios no .env")
        return

    mode = "DRY RUN" if args.dry_run else "REAL"
    logger.info(f"=== Modo {mode} | Origem: {SUPABASE_URL}")

    results = {
        "contacts": await migrate_contacts(args.dry_run),
        "novos_convertidos": await migrate_novos_convertidos(args.dry_run),
        "eventos_paes": await migrate_eventos(args.dry_run),
        "plano_de_leitura": await migrate_plano_leitura(args.dry_run),
        "knowledge_chunks": await migrate_knowledge(args.dry_run),
        "liderancas": await migrate_liderancas(args.dry_run),
        "pastores_aniversario": await migrate_pastores(args.dry_run),
        "paes_atendimentos_log": await migrate_atendimentos_log(args.dry_run),
        "llm_analytics": await migrate_analytics(args.dry_run),
    }
    if args.include_history:
        results["messages (chat history)"] = await migrate_chat_history(args.dry_run)

    logger.info("===== RESULTADO =====")
    for k, v in results.items():
        logger.info(f"  {k:30} {v:>8}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
