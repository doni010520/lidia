"""Serviço OpenAI — chat completion com tool-calling loop.

O loop executa até MAX_ITERATIONS de chamadas de tools.
Na Fase 2, tools=[] — o loop encerra na primeira resposta.
A partir da Fase 3, tools serão passadas e o loop executará handlers.
"""
from __future__ import annotations

import json
from typing import Any

import openai
from loguru import logger

from app.core.config import settings

MAX_ITERATIONS = 10


class OpenAIService:

    def __init__(self) -> None:
        self._client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

    async def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        system_prompt: str,
        tools: list[dict] | None = None,
        phone: str = "",
        tool_handler: Any | None = None,
    ) -> tuple[str, list[dict[str, Any]], list[str]]:
        """Executa chat completion com tool-calling loop.

        Args:
            messages: histórico de conversa (role/content dicts)
            system_prompt: system prompt completo já renderizado
            tools: lista de tool schemas OpenAI (vazia = sem tools)
            phone: telefone do contato (para context nos handlers)
            tool_handler: callable async (tool_name, args, phone, db) → str
                          Será implementado na Fase 3.

        Returns:
            (reply_text, updated_messages, tools_called)
        """
        log = logger.bind(phone=phone)

        # Montar mensagens completas com system
        full_messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            *messages,
        ]

        tools_called: list[str] = []
        active_tools = tools if tools else None

        for iteration in range(MAX_ITERATIONS):
            try:
                kwargs: dict[str, Any] = {
                    "model": settings.openai_model,
                    "messages": full_messages,
                    "temperature": settings.openai_temperature,
                    "max_tokens": settings.openai_max_tokens,
                }
                if active_tools:
                    kwargs["tools"] = active_tools

                response = await self._client.chat.completions.create(**kwargs)

            except openai.APIError as exc:
                log.error(f"OpenAI API error: {exc}")
                return self._fallback_message(), messages, tools_called

            choice = response.choices[0]
            assistant_msg = choice.message

            # ── Resposta final (sem tool calls) ──
            if not assistant_msg.tool_calls:
                reply = assistant_msg.content or ""
                # Salvar mensagem do assistant no histórico
                messages.append({"role": "assistant", "content": reply})
                log.info(f"LLM respondeu ({response.usage.total_tokens}t, iter={iteration})")
                return reply, messages, tools_called

            # ── Tool calls ──
            # Serializar tool_calls para persistência
            tc_serialized = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in assistant_msg.tool_calls
            ]

            messages.append({
                "role": "assistant",
                "content": assistant_msg.content or "",
                "tool_calls": tc_serialized,
            })
            full_messages.append({
                "role": "assistant",
                "content": assistant_msg.content or "",
                "tool_calls": tc_serialized,
            })

            # Executar cada tool call
            for tc in assistant_msg.tool_calls:
                tool_name = tc.function.name
                tools_called.append(tool_name)

                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                log.info(f"Tool call: {tool_name}({list(args.keys())})")

                # Executar handler (Fase 3+)
                if tool_handler:
                    try:
                        result = await tool_handler(tool_name, args, phone)
                    except Exception as exc:
                        log.exception(f"Erro no handler da tool {tool_name}")
                        result = f"Erro ao executar {tool_name}: {str(exc)}"
                else:
                    result = f"Tool {tool_name} não implementada ainda."

                tool_result_msg = {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": str(result),
                }
                messages.append(tool_result_msg)
                full_messages.append(tool_result_msg)

        # Excedeu MAX_ITERATIONS
        log.warning(f"Tool loop excedeu {MAX_ITERATIONS} iterações")
        return self._fallback_message(), messages, tools_called

    @staticmethod
    def _fallback_message() -> str:
        return (
            "Desculpe, tive um problema ao processar sua mensagem. "
            "Vou encaminhar para nossa equipe. Um momento! 🙏"
        )
