"""Singleton holders para serviços compartilhados.

Inicializados no lifespan do FastAPI e acessados via funções get_*.
"""
from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from app.services.buffer_service import BufferService
from app.services.uaz_client import UAZClient

_buffer_service: BufferService | None = None
_uaz_client: UAZClient | None = None
_process_callback: Callable[[str], Coroutine[Any, Any, None]] | None = None


def init_services(
    buffer: BufferService,
    uaz: UAZClient,
    process_cb: Callable[[str], Coroutine[Any, Any, None]],
) -> None:
    global _buffer_service, _uaz_client, _process_callback
    _buffer_service = buffer
    _uaz_client = uaz
    _process_callback = process_cb


def get_buffer_service() -> BufferService:
    assert _buffer_service is not None, "BufferService não inicializado"
    return _buffer_service


def get_uaz_client() -> UAZClient:
    assert _uaz_client is not None, "UAZClient não inicializado"
    return _uaz_client


def get_process_callback() -> Callable[[str], Coroutine[Any, Any, None]]:
    assert _process_callback is not None, "process_callback não registrado"
    return _process_callback
