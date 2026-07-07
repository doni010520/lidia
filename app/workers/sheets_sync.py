"""Worker: sheets_sync — sincroniza Google Sheets → DB.

Roda a cada SHEETS_SYNC_INTERVAL_MINUTES via APScheduler.
Três tarefas: sync_eventos, sync_informacoes, sync_plano_leitura.
"""
from __future__ import annotations

from datetime import date, time

from loguru import logger
from sqlalchemy import text

from app.core.config import settings
from app.db import async_session_factory
from app.services import sheets_client


def _parse_date(s: str | None) -> date | None:
    """Parse data em formatos comuns (YYYY-MM-DD, DD/MM/YYYY)."""
    if not s or not s.strip():
        return None
    s = s.strip()
    # Tentar ISO primeiro
    try:
        return date.fromisoformat(s)
    except ValueError:
        pass
    # Tentar DD/MM/YYYY
    try:
        parts = s.split("/")
        if len(parts) == 3:
            return date(int(parts[2]), int(parts[1]), int(parts[0]))
    except (ValueError, IndexError):
        pass
    return None


def _parse_time(s: str | None) -> time | None:
    """Parse horário (HH:MM ou HH:MM:SS)."""
    if not s or not s.strip():
        return None
    s = s.strip()
    try:
        parts = s.split(":")
        return time(int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return None


async def sync_eventos() -> int:
    """Sincroniza planilha de eventos → tabela eventos_paes."""
    sheet_id = settings.sheets_eventos_id
    if not sheet_id:
        logger.debug("SHEETS_EVENTOS_ID não configurado, pulando sync")
        return 0

    try:
        rows = sheets_client.read_all(sheet_id)
    except Exception:
        logger.exception("Erro ao ler Sheets de eventos")
        return 0

    if not rows:
        return 0

    count = 0
    async with async_session_factory() as db:
        for row in rows:
            nome = row.get("Nome", row.get("nome", row.get("Evento", ""))).strip()
            if not nome:
                continue

            row_id = str(row.get("_row_number", ""))
            descricao = row.get("Descrição", row.get("descricao", ""))
            local = row.get("Local", row.get("local", ""))
            data_inicio = _parse_date(row.get("Data Início", row.get("data_inicio", row.get("Data", ""))))
            data_final = _parse_date(row.get("Data Final", row.get("data_final", row.get("Data Fim", ""))))
            hora = _parse_time(row.get("Horário", row.get("hora", row.get("Hora", ""))))
            valor = row.get("Valor", row.get("valor", ""))
            link = row.get("Link", row.get("link", ""))
            media = row.get("Media", row.get("media", row.get("Imagem", "")))

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
                        media = EXCLUDED.media
                """),
                {
                    "nome": nome,
                    "descricao": descricao,
                    "local": local,
                    "data_inicio": data_inicio,
                    "data_final": data_final or data_inicio,
                    "hora": hora,
                    "valor": valor,
                    "link": link,
                    "media": media,
                    "sheets_row_id": row_id,
                },
            )
            count += 1

        await db.commit()

    logger.info(f"Sheets sync eventos: {count} rows processadas")
    return count


async def sync_plano_leitura() -> int:
    """Sincroniza planilha do plano de leitura → tabela plano_de_leitura."""
    sheet_id = settings.sheets_plano_leitura_id
    if not sheet_id:
        logger.debug("SHEETS_PLANO_LEITURA_ID não configurado, pulando sync")
        return 0

    try:
        rows = sheets_client.read_all(sheet_id)
    except Exception:
        logger.exception("Erro ao ler Sheets do plano de leitura")
        return 0

    if not rows:
        return 0

    count = 0
    async with async_session_factory() as db:
        for row in rows:
            data = _parse_date(row.get("Data", row.get("data", "")))
            if not data:
                continue

            leitura = row.get("Leitura", row.get("leitura", ""))
            capitulos = row.get("Capítulos", row.get("capitulos", row.get("Capitulos", "")))
            semana_str = row.get("Semana", row.get("semana", ""))
            livro = row.get("Livro", row.get("livro", ""))
            row_id = str(row.get("_row_number", ""))

            semana: int | None = None
            if semana_str:
                try:
                    semana = int(semana_str)
                except ValueError:
                    pass

            await db.execute(
                text("""
                    INSERT INTO plano_de_leitura
                        (data, leitura, capitulos, semana, livro, sheets_row_id)
                    VALUES
                        (:data, :leitura, :capitulos, :semana, :livro, :sheets_row_id)
                    ON CONFLICT (data) DO UPDATE SET
                        leitura = EXCLUDED.leitura,
                        capitulos = EXCLUDED.capitulos,
                        semana = EXCLUDED.semana,
                        livro = EXCLUDED.livro,
                        sheets_row_id = EXCLUDED.sheets_row_id
                """),
                {
                    "data": data,
                    "leitura": leitura,
                    "capitulos": capitulos,
                    "semana": semana,
                    "livro": livro,
                    "sheets_row_id": row_id,
                },
            )
            count += 1

        await db.commit()

    logger.info(f"Sheets sync plano leitura: {count} rows processadas")
    return count


async def sync_informacoes() -> int:
    """Sincroniza planilha de informações → knowledge_chunks (RAG).

    Cada linha vira um chunk vetorizado.
    """
    sheet_id = settings.sheets_informacoes_id
    if not sheet_id:
        logger.debug("SHEETS_INFORMACOES_ID não configurado, pulando sync")
        return 0

    try:
        rows = sheets_client.read_all(sheet_id)
    except Exception:
        logger.exception("Erro ao ler Sheets de informações")
        return 0

    if not rows:
        return 0

    # Montar textos para vectorizar
    texts: list[dict] = []
    for row in rows:
        pergunta = (row.get("Pergunta") or row.get("pergunta")
                    or row.get("Perguntas") or row.get("perguntas") or "")
        resposta = (row.get("Resposta") or row.get("resposta")
                    or row.get("Respostas") or row.get("respostas") or "")
        if not pergunta and not resposta:
            continue
        content = f"Pergunta: {pergunta}\nResposta: {resposta}" if pergunta else resposta
        texts.append({"content": content, "source": "sheets_informacoes"})

    if not texts:
        return 0

    # Embed + insert
    import openai
    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

    async with async_session_factory() as db:
        # Limpar chunks dessa fonte antes de reinserir
        await db.execute(
            text("DELETE FROM knowledge_chunks WHERE source = 'sheets_informacoes'")
        )

        for i in range(0, len(texts), 100):
            batch = texts[i:i + 100]
            batch_texts = [t["content"] for t in batch]

            resp = await client.embeddings.create(
                model=settings.openai_embedding_model,
                input=batch_texts,
            )

            # A OpenAI pode devolver os embeddings fora de ordem — reordena por index
            # antes de associar, senão o vetor gruda na linha errada.
            data_ordenada = sorted(resp.data, key=lambda d: d.index)

            import json
            for t, emb_data in zip(batch, data_ordenada):
                await db.execute(
                    text("""
                        INSERT INTO knowledge_chunks (content, embedding, metadata, source)
                        VALUES (:content, CAST(:embedding AS vector), CAST(:metadata AS jsonb), :source)
                    """),
                    {
                        "content": t["content"],
                        "embedding": str(emb_data.embedding),
                        "metadata": json.dumps({"source": "sheets_informacoes"}),
                        "source": "sheets_informacoes",
                    },
                )

        await db.commit()

    logger.info(f"Sheets sync informações: {len(texts)} chunks vetorizados")
    return len(texts)


async def run_all_syncs() -> dict[str, int]:
    """Executa todas as sincronizações. Chamado pelo APScheduler."""
    logger.info("Iniciando sync de Sheets...")
    results = {
        "eventos": await sync_eventos(),
        "plano_leitura": await sync_plano_leitura(),
        "informacoes": await sync_informacoes(),
    }
    logger.info(f"Sync completo: {results}")
    return results
