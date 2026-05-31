"""Analytics service — rastreia tokens, custo, intent e sentimento.

Cada chamada LLM gera uma linha em llm_analytics.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from loguru import logger
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.analytics import LLMAnalytics

# Custo gpt-4.1-mini (por token)
_COST_INPUT = 0.0000004
_COST_OUTPUT = 0.0000016

# Estimativa de chars do system prompt para cálculo de tokens
_SYSTEM_CHARS_ESTIMATE = 15000

# Palavras de sentimento (simplificado)
_POSITIVE = {"obrigado", "obrigada", "amém", "amen", "deus", "bênção", "bencao", "paz",
             "alegria", "feliz", "maravilhoso", "excelente", "ótimo", "bom"}
_NEGATIVE = {"triste", "problema", "difícil", "dificil", "dor", "sofrimento", "medo",
             "angústia", "angustia", "preocupado", "ansioso", "ansiedade", "depressão"}


@dataclass
class AnalyticsContext:
    phone: str
    agent_type: str
    start_time: float = field(default_factory=time.time)
    input_text: str = ""


def start(*, phone: str, agent_type: str, input_text: str = "") -> AnalyticsContext:
    """Inicia contexto de analytics para uma interação."""
    return AnalyticsContext(
        phone=phone,
        agent_type=agent_type,
        input_text=input_text,
    )


def _calc_sentiment(text: str) -> float:
    """Calcula score de sentimento simplificado (0.0 a 1.0)."""
    words = set(text.lower().split())
    pos = len(words & _POSITIVE)
    neg = len(words & _NEGATIVE)
    total = pos + neg
    if total == 0:
        return 0.5  # neutro
    return round(pos / total, 2)


async def capture(
    ctx: AnalyticsContext,
    reply_text: str,
    tools_called: list[str],
    db: AsyncSession,
) -> None:
    """Captura métricas e persiste em llm_analytics."""
    response_time_ms = int((time.time() - ctx.start_time) * 1000)

    # Estimar tokens (4 chars ≈ 1 token)
    prompt_tokens = (len(ctx.input_text) + _SYSTEM_CHARS_ESTIMATE) // 4
    completion_tokens = len(reply_text) // 4
    total_tokens = prompt_tokens + completion_tokens

    cost_usd = prompt_tokens * _COST_INPUT + completion_tokens * _COST_OUTPUT

    sentiment = _calc_sentiment(ctx.input_text)
    intent = tools_called[0] if tools_called else "conversa_geral"

    try:
        await db.execute(
            insert(LLMAnalytics).values(
                session_id=ctx.phone,
                model_name=settings.openai_model,
                agent_type=ctx.agent_type,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                cost_usd=cost_usd,
                intent_detected=intent,
                sentiment_score=sentiment,
                response_time_ms=response_time_ms,
                tools_called=tools_called or None,
            )
        )
        # flush — o commit final é do pipeline
        await db.flush()
    except Exception:
        logger.exception("Erro ao salvar analytics")
