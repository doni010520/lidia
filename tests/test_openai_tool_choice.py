"""tool_choice forçado vale só na primeira volta do loop.

Se valesse em todas, o modelo seria obrigado a chamar a ferramenta de novo
depois de receber o resultado — e o loop só acabaria em MAX_ITERATIONS.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.openai_service import OpenAIService

FORCA = {"type": "function", "function": {"name": "buscar_evento"}}


def _resp(content="", tool=None):
    tool_calls = None
    if tool:
        tool_calls = [SimpleNamespace(id="c1", function=SimpleNamespace(name=tool, arguments="{}"))]
    msg = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=SimpleNamespace(total_tokens=1))


class _FakeCompletions:
    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.respostas.pop(0)


def _svc(fake):
    svc = OpenAIService.__new__(OpenAIService)
    svc._client = SimpleNamespace(chat=SimpleNamespace(completions=fake))
    return svc


@pytest.mark.asyncio
async def test_tool_choice_so_na_primeira_volta():
    fake = _FakeCompletions([_resp(tool="buscar_evento"), _resp(content="pronto")])

    async def handler(name, args, phone):
        return "Encontrados 1 evento(s)"

    reply, _, called = await _svc(fake).chat(
        messages=[{"role": "user", "content": "oi"}], system_prompt="SYS",
        tools=[{"type": "function", "function": {"name": "buscar_evento"}}],
        phone="5581", tool_handler=handler, tool_choice=FORCA,
    )

    assert fake.calls[0]["tool_choice"] == FORCA
    assert "tool_choice" not in fake.calls[1]
    assert reply == "pronto"
    assert called == ["buscar_evento"]


@pytest.mark.asyncio
async def test_sem_tool_choice_nada_muda():
    fake = _FakeCompletions([_resp(content="oi")])
    await _svc(fake).chat(
        messages=[{"role": "user", "content": "oi"}], system_prompt="SYS",
        tools=[{"type": "function", "function": {"name": "buscar_evento"}}],
        phone="5581", tool_handler=None,
    )
    assert "tool_choice" not in fake.calls[0]
