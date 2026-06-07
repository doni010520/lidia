from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Coroutine
from typing import Any

import redis.asyncio as aioredis
from loguru import logger

from app.core.config import settings
from app.schemas.webhook import IncomingMessage

# Prefixos Redis
_BUFFER_KEY = "lidia:buffer:{phone}"
_LOCK_KEY = "lidia:lock:{phone}"
_DEDUP_KEY = "lidia:dedup:{msg_id}"


class BufferService:
    """Debounce de mensagens por telefone usando Redis.

    Agrega mensagens recebidas em rajada (10s) antes de processar.
    """

    def __init__(self) -> None:
        self.redis: aioredis.Redis | None = None
        self.buffer_seconds = settings.redis_buffer_seconds
        self._pending_tasks: dict[str, asyncio.Task] = {}

    async def connect(self) -> None:
        self.redis = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
        logger.info("BufferService conectado ao Redis")

    async def close(self) -> None:
        if self.redis:
            await self.redis.close()

    async def is_duplicate(self, message_id: str) -> bool:
        """Verifica e registra message_id para idempotência (TTL 5min)."""
        if not message_id or not self.redis:
            return False
        key = _DEDUP_KEY.format(msg_id=message_id)
        was_set = await self.redis.set(key, "1", nx=True, ex=300)
        return not was_set  # True se já existia

    async def push(
        self,
        msg: IncomingMessage,
        callback: Callable[[str], Coroutine[Any, Any, None]],
    ) -> None:
        """Adiciona mensagem ao buffer e agenda processamento após debounce.

        O callback recebe o telefone e deve buscar as mensagens acumuladas.
        """
        if not self.redis:
            raise RuntimeError("BufferService não conectado")

        phone = msg.phone
        buf_key = _BUFFER_KEY.format(phone=phone)

        entry = json.dumps({
            "text": msg.text,
            "media_url": msg.media_url,
            "media_type": msg.media_type,
            "media_key": msg.media_key,
            "mimetype": msg.mimetype,
            "message_id": msg.message_id,
            "name": msg.name,
            "latitude": msg.latitude,
            "longitude": msg.longitude,
        })
        await self.redis.rpush(buf_key, entry)
        await self.redis.expire(buf_key, self.buffer_seconds + 30)

        # Cancela timer anterior e recria (debounce)
        existing = self._pending_tasks.get(phone)
        if existing and not existing.done():
            existing.cancel()

        task = asyncio.create_task(self._schedule(phone, callback))
        self._pending_tasks[phone] = task

    async def _schedule(
        self,
        phone: str,
        callback: Callable[[str], Coroutine[Any, Any, None]],
    ) -> None:
        """Espera o debounce e dispara o callback."""
        await asyncio.sleep(self.buffer_seconds)
        try:
            await callback(phone)
        except Exception:
            logger.exception(f"Erro no callback de buffer para {phone}")
        finally:
            self._pending_tasks.pop(phone, None)

    async def pop_all(self, phone: str) -> list[dict]:
        """Consome todas as mensagens acumuladas de um telefone."""
        if not self.redis:
            return []

        buf_key = _BUFFER_KEY.format(phone=phone)
        pipe = self.redis.pipeline()
        pipe.lrange(buf_key, 0, -1)
        pipe.delete(buf_key)
        results = await pipe.execute()

        raw_list: list[str] = results[0] or []
        return [json.loads(r) for r in raw_list]

    async def aggregate_text(self, phone: str) -> tuple[str, IncomingMessage | None]:
        """Consome buffer e retorna texto agregado + último IncomingMessage (para mídia)."""
        entries = await self.pop_all(phone)
        if not entries:
            return "", None

        texts: list[str] = []
        last_media: dict | None = None

        for entry in entries:
            if entry.get("text"):
                texts.append(entry["text"])
            if entry.get("media_url"):
                last_media = entry

        aggregated = "\n".join(texts)

        # Localização: pega a última entry que trouxe lat/lng
        last_loc = None
        for entry in entries:
            if entry.get("latitude") is not None and entry.get("longitude") is not None:
                last_loc = entry

        last_msg: IncomingMessage | None = None
        if last_media:
            last_msg = IncomingMessage(
                phone=phone,
                name=last_media.get("name"),
                text=aggregated if aggregated else None,
                media_url=last_media.get("media_url"),
                media_type=last_media.get("media_type"),
                media_key=last_media.get("media_key"),
                mimetype=last_media.get("mimetype"),
                message_id=last_media.get("message_id"),
                latitude=last_loc["latitude"] if last_loc else None,
                longitude=last_loc["longitude"] if last_loc else None,
            )
        elif aggregated or last_loc:
            first = entries[0]
            last_msg = IncomingMessage(
                phone=phone,
                name=first.get("name"),
                text=aggregated if aggregated else None,
                message_id=entries[-1].get("message_id"),
                latitude=last_loc["latitude"] if last_loc else None,
                longitude=last_loc["longitude"] if last_loc else None,
            )

        return aggregated, last_msg
