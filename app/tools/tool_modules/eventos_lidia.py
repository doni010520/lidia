"""Tool: eventos_Lidia — ADMIN: CRUD de eventos no banco."""
from __future__ import annotations

from datetime import date, time

from loguru import logger
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.eventos import EventoPaes


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _parse_time(s: str | None) -> time | None:
    if not s:
        return None
    try:
        parts = s.split(":")
        return time(int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return None


async def execute(
    args: dict,
    phone: str,
    db: AsyncSession,
) -> str:
    funcao = args.get("funcao", "")
    nome = args.get("Nome", args.get("nome", ""))

    if not nome:
        return "Erro: 'Nome' é obrigatório."
    if funcao not in ("cadastrar", "atualizar", "deletar"):
        return "Erro: 'funcao' deve ser 'cadastrar', 'atualizar' ou 'deletar'."

    if funcao == "deletar":
        result = await db.execute(
            delete(EventoPaes).where(EventoPaes.nome.ilike(f"%{nome}%"))
        )
        await db.commit()
        return f"Evento(s) contendo '{nome}' deletado(s): {result.rowcount} registro(s)."

    # Campos comuns
    data_inicio = _parse_date(args.get("Data_inicio"))
    data_final = _parse_date(args.get("Data_final"))
    hora = _parse_time(args.get("Hora"))

    if funcao == "atualizar":
        # UPDATE explícito por nome (ILIKE)
        result = await db.execute(
            text("""
                UPDATE eventos_paes SET
                    descricao = COALESCE(NULLIF(:descricao, ''), descricao),
                    local = COALESCE(NULLIF(:local, ''), local),
                    data_inicio = COALESCE(:data_inicio, data_inicio),
                    data_final = COALESCE(:data_final, data_final),
                    hora = COALESCE(:hora, hora),
                    valor = COALESCE(NULLIF(:valor, ''), valor),
                    link = COALESCE(NULLIF(:link, ''), link),
                    media = COALESCE(NULLIF(:media, ''), media),
                    updated_at = NOW()
                WHERE nome ILIKE :nome_pattern
            """),
            {
                "nome_pattern": f"%{nome}%",
                "descricao": args.get("Descricao", ""),
                "local": args.get("Local", ""),
                "data_inicio": data_inicio,
                "data_final": data_final,
                "hora": hora,
                "valor": args.get("Valor", ""),
                "link": args.get("Link", ""),
                "media": args.get("media", ""),
            },
        )
        await db.commit()
        if result.rowcount == 0:
            return f"Nenhum evento encontrado com nome '{nome}' para atualizar."
        logger.info(f"Evento atualizado: {nome} ({result.rowcount} registro(s))")
        return f"Evento '{nome}' atualizado com sucesso ({result.rowcount} registro(s))."

    # cadastrar — gerar sheets_row_id determinístico para evitar duplicatas
    row_id = f"admin:{nome.lower().strip()}:{data_inicio or 'sem-data'}"

    await db.execute(
        text("""
            INSERT INTO eventos_paes
                (nome, descricao, local, data_inicio, data_final, hora, valor, link, media, sheets_row_id)
            VALUES
                (:nome, :descricao, :local, :data_inicio, :data_final, :hora, :valor, :link, :media, :sheets_row_id)
            ON CONFLICT (sheets_row_id) DO UPDATE SET
                nome = EXCLUDED.nome,
                descricao = EXCLUDED.descricao,
                local = EXCLUDED.local,
                data_inicio = EXCLUDED.data_inicio,
                data_final = EXCLUDED.data_final,
                hora = EXCLUDED.hora,
                valor = EXCLUDED.valor,
                link = EXCLUDED.link,
                media = EXCLUDED.media,
                updated_at = NOW()
        """),
        {
            "nome": nome,
            "descricao": args.get("Descricao", ""),
            "local": args.get("Local", ""),
            "data_inicio": data_inicio,
            "data_final": data_final or data_inicio,
            "hora": hora,
            "valor": args.get("Valor", ""),
            "link": args.get("Link", ""),
            "media": args.get("media", ""),
            "sheets_row_id": row_id,
        },
    )
    await db.commit()
    logger.info(f"Evento cadastrado: {nome} (row_id={row_id})")
    return f"Evento '{nome}' cadastrado com sucesso."
