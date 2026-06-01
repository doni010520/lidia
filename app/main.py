from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
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
    # sink temporário para debug (remove após bateria de testes)
    try:
        from app.api.debug_stats import _log_sink
        logger.add(_log_sink, level="DEBUG", format="{message}")
    except Exception:
        pass
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

    # ── Disparo scheduler (a cada 1min) ──
    from app.workers.disparo_scheduler import check_scheduled_disparos
    scheduler.add_job(
        check_scheduled_disparos,
        "interval",
        minutes=1,
        id="disparo_scheduler",
        name="Disparos agendados → executar",
        misfire_grace_time=60,
    )
    logger.info("Disparo scheduler agendado a cada 1min")

    # ── Aniversariantes (diário 8h BR) ──
    from app.workers.aniversarios import check_aniversariantes
    scheduler.add_job(
        check_aniversariantes,
        "cron",
        hour=8, minute=0,
        timezone="America/Sao_Paulo",
        id="aniversarios",
        name="Aniversariantes do dia",
        misfire_grace_time=3600,
    )
    logger.info("Aniversariantes agendado diariamente as 8h BR")

    # ── Disparo Lideranças (terças 9h BR) ──
    from app.workers.disparo_liderancas import disparar_liderancas
    scheduler.add_job(
        disparar_liderancas,
        "cron",
        day_of_week="tue", hour=9, minute=0,
        timezone="America/Sao_Paulo",
        id="disparo_liderancas",
        name="Disparo semanal para liderancas",
        misfire_grace_time=3600,
    )
    logger.info("Disparo de liderancas agendado para tercas 9h BR")

    # ── Boas-vindas a novos convertidos (segundas 10h BR) ──
    from app.workers.boas_vindas_convertidos import disparar_boas_vindas
    scheduler.add_job(
        disparar_boas_vindas,
        "cron",
        day_of_week="mon", hour=10, minute=0,
        timezone="America/Sao_Paulo",
        id="boas_vindas_convertidos",
        name="Boas-vindas a novos convertidos",
        misfire_grace_time=3600,
    )
    logger.info("Boas-vindas a convertidos agendado para segundas 10h BR")

    # ── Gerar cultos dominicais (dia 1 do mes, 1h BR) ──
    from app.workers.cultos_gerador import gerar_cultos_proximos_meses
    scheduler.add_job(
        gerar_cultos_proximos_meses,
        "cron",
        day=1, hour=1, minute=0,
        timezone="America/Sao_Paulo",
        id="cultos_gerador",
        name="Gerar cultos dominicais",
        misfire_grace_time=86400,
    )
    logger.info("Cultos dominicais agendado para dia 1 as 1h BR")

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
    from app.api.auth import router as auth_router
    from app.api.disparos import router as disparos_router
    from app.api.eventos import router as eventos_router
    from app.api.debug_stats import router as debug_router

    app.include_router(webhook_router)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(disparos_router)
    app.include_router(eventos_router)
    app.include_router(debug_router)

    # Servir estáticos DEPOIS dos routers (API tem prioridade)
    app.mount("/", StaticFiles(directory="app/static", html=True), name="static")

    return app


app = create_app()
