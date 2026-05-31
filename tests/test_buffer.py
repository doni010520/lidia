"""Testes para o BufferService — debounce e agregação."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.webhook import IncomingMessage
from app.services.buffer_service import BufferService


@pytest.fixture
def mock_redis():
    """Mock do Redis com storage em memória."""
    storage: dict[str, list] = {}

    redis = AsyncMock()

    async def rpush(key, value):
        storage.setdefault(key, []).append(value)

    async def lrange(key, start, end):
        return storage.get(key, [])

    async def delete(key):
        storage.pop(key, None)

    async def expire(key, ttl):
        pass

    async def set_cmd(key, value, nx=False, ex=None):
        if nx and key in storage:
            return None
        storage[key] = [value]
        return True

    redis.rpush = rpush
    redis.lrange = lrange
    redis.delete = delete
    redis.expire = expire
    redis.set = set_cmd

    # Pipeline mock — pipeline() é sync no redis.asyncio, retorna objeto com métodos sync
    # mas execute() é async
    class FakePipeline:
        def __init__(self):
            self._ops = []

        def lrange(self, key, start, end):
            self._ops.append(("lrange", key))
            return self

        def delete(self, key):
            self._ops.append(("delete", key))
            return self

        async def execute(self):
            results = []
            for op, key in self._ops:
                if op == "lrange":
                    results.append(storage.get(key, []))
                elif op == "delete":
                    storage.pop(key, None)
                    results.append(1)
            self._ops.clear()
            return results

    # pipeline() deve ser sync (não coroutine)
    redis.pipeline = MagicMock(side_effect=lambda: FakePipeline())

    return redis, storage


@pytest.fixture
def buffer_service(mock_redis, monkeypatch):
    monkeypatch.setattr("app.services.buffer_service.settings", MagicMock(
        redis_url="redis://fake:6379",
        redis_buffer_seconds=1,  # 1s para testes rápidos
    ))
    svc = BufferService()
    svc.redis = mock_redis[0]
    svc.buffer_seconds = 1
    return svc


def _msg(phone: str, text: str, msg_id: str = "M1") -> IncomingMessage:
    return IncomingMessage(phone=phone, name="Teste", text=text, message_id=msg_id)


class TestBufferDedup:
    @pytest.mark.asyncio
    async def test_first_message_not_duplicate(self, buffer_service):
        assert await buffer_service.is_duplicate("MSG001") is False

    @pytest.mark.asyncio
    async def test_second_message_is_duplicate(self, buffer_service):
        await buffer_service.is_duplicate("MSG001")
        assert await buffer_service.is_duplicate("MSG001") is True

    @pytest.mark.asyncio
    async def test_different_ids_not_duplicate(self, buffer_service):
        await buffer_service.is_duplicate("MSG001")
        assert await buffer_service.is_duplicate("MSG002") is False


class TestBufferAggregation:
    @pytest.mark.asyncio
    async def test_aggregate_single_text(self, buffer_service, mock_redis):
        callback = AsyncMock()
        await buffer_service.push(_msg("5581999", "Olá"), callback)
        # Esperar debounce (1s + margem)
        await asyncio.sleep(1.5)

        text, msg = await buffer_service.aggregate_text("5581999")
        # O callback já consumiu, mas vamos testar direto com push + pop
        assert callback.called

    @pytest.mark.asyncio
    async def test_aggregate_three_messages(self, buffer_service, mock_redis):
        """Simula 3 mensagens em rajada, verifica agregação."""
        callback = AsyncMock()

        await buffer_service.push(_msg("5581999", "Olá", "M1"), callback)
        await buffer_service.push(_msg("5581999", "Tudo bem?", "M2"), callback)
        await buffer_service.push(_msg("5581999", "Preciso de ajuda", "M3"), callback)

        # O pop_all deve retornar as 3
        entries = await buffer_service.pop_all("5581999")
        assert len(entries) == 3
        assert entries[0]["text"] == "Olá"
        assert entries[1]["text"] == "Tudo bem?"
        assert entries[2]["text"] == "Preciso de ajuda"

    @pytest.mark.asyncio
    async def test_aggregate_text_concatenation(self, buffer_service, mock_redis):
        """Verifica que aggregate_text junta textos com newline."""
        # Push direto no Redis (simulando 3 msgs)
        buf_key = "lidia:buffer:5581999"
        for txt in ["Olá", "Tudo bem?", "Preciso de ajuda"]:
            await buffer_service.redis.rpush(buf_key, json.dumps({
                "text": txt, "media_url": None, "media_type": None,
                "media_key": None, "mimetype": None, "message_id": "X",
                "name": "Teste",
            }))

        text, msg = await buffer_service.aggregate_text("5581999")
        assert text == "Olá\nTudo bem?\nPreciso de ajuda"
        assert msg is not None
        assert msg.phone == "5581999"
        assert msg.text == "Olá\nTudo bem?\nPreciso de ajuda"

    @pytest.mark.asyncio
    async def test_aggregate_with_media(self, buffer_service, mock_redis):
        """Texto + mídia: retorna IncomingMessage com media_url."""
        buf_key = "lidia:buffer:5581999"
        await buffer_service.redis.rpush(buf_key, json.dumps({
            "text": "Olha isso", "media_url": None, "media_type": None,
            "media_key": None, "mimetype": None, "message_id": "M1",
            "name": "Teste",
        }))
        await buffer_service.redis.rpush(buf_key, json.dumps({
            "text": None, "media_url": "https://img.jpg", "media_type": "image",
            "media_key": "abc", "mimetype": "image/jpeg", "message_id": "M2",
            "name": "Teste",
        }))

        text, msg = await buffer_service.aggregate_text("5581999")
        assert text == "Olha isso"
        assert msg is not None
        assert msg.media_url == "https://img.jpg"
        assert msg.media_type == "image"

    @pytest.mark.asyncio
    async def test_aggregate_empty_buffer(self, buffer_service):
        text, msg = await buffer_service.aggregate_text("5581000")
        assert text == ""
        assert msg is None
