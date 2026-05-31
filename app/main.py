from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from loguru import logger

from app.core.config import settings


def _setup_logging() -> None:
    logger.remove()
    fmt = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "{extra} | "
        "<level>{message}</level>"
    )
    logger.add(sys.stderr, format=fmt, level=settings.log_level)
    if settings.env == "production":
        logger.add(
            sys.stdout,
            serialize=True,
            level=settings.log_level,
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup / Shutdown."""
    _setup_logging()
    logger.info(f"Iniciando {settings.agent_name} ({settings.env})")

    # ── Serviços ──
    from app.services.buffer_service import BufferService
    from app.services.uaz_client import UAZClient
    from app.services.deps import init_services

    buffer = BufferService()
    await buffer.connect()

    uaz = UAZClient()

    # Callback real — consome buffer, monta IncomingMessage, roda pipeline
    async def _process_buffered(phone: str) -> None:
        from app.services.conversation_service import process_message
        from app.db import async_session_factory

        aggregated, last_msg = await buffer.aggregate_text(phone)
        if not last_msg:
            return

        async with async_session_factory() as db:
            try:
                await process_message(last_msg, db)
            except Exception:
                logger.bind(phone=phone).exception("Erro no pipeline de conversação")

    init_services(buffer=buffer, uaz=uaz, process_cb=_process_buffered)

    # ── uazapi chatbot settings (handoff nativo) ──
    if settings.uaz_base_url and settings.uaz_token:
        try:
            await uaz.update_chatbot_settings(
                chatbot_enabled=True,
                chatbot_ignore_groups=True,
                chatbot_stop_when_you_send_msg=settings.handoff_pause_minutes,
            )
            logger.info(f"uazapi chatbot configurado (pause={settings.handoff_pause_minutes}min)")
        except Exception:
            logger.warning("Falha ao configurar chatbot settings na uazapi (startup)")

    # ── APScheduler — workers periódicos ──
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    scheduler = AsyncIOScheduler()

    if settings.sheets_eventos_id or settings.sheets_plano_leitura_id or settings.sheets_informacoes_id:
        from app.workers.sheets_sync import run_all_syncs
        scheduler.add_job(
            run_all_syncs,
            "interval",
            minutes=settings.sheets_sync_interval_minutes,
            id="sheets_sync",
            name="Sheets → DB sync",
            misfire_grace_time=60,
        )
        logger.info(f"Sheets sync agendado a cada {settings.sheets_sync_interval_minutes}min")

    if settings.sheets_log_oracao_id:
        from app.workers.oracao_responder import check_and_send
        scheduler.add_job(
            check_and_send,
            "interval",
            minutes=5,
            id="oracao_responder",
            name="Oração → envio de respostas",
            misfire_grace_time=60,
        )
        logger.info("Oracao responder agendado a cada 5min")

    scheduler.start()
    logger.info(f"APScheduler iniciado ({len(scheduler.get_jobs())} jobs)")

    yield

    # ── Shutdown ──
    logger.info("Encerrando serviços...")
    scheduler.shutdown(wait=False)
    await uaz.close()
    await buffer.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.agent_name,
        version="1.0.0",
        lifespan=lifespan,
    )

    from app.api.webhooks import router as webhook_router
    from app.api.health import router as health_router

    app.include_router(webhook_router)
    app.include_router(health_router)

    return app


app = create_app()
