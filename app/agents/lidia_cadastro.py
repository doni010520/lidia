"""Agente de cadastro LidIA — acolhe leads novos e coleta dados.

Fase 3: tool cadastrar_contato habilitada.
"""
from __future__ import annotations

from pathlib import Path

from app.tools.registry import get_tools

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "lidia_cadastro_system.txt"
_raw_prompt: str | None = None

TOOLS_ALLOWED: list[str] = [
    "cadastrar_contato",
]
tools_allowed: list[dict] = get_tools(TOOLS_ALLOWED)


def _load_raw() -> str:
    global _raw_prompt
    if _raw_prompt is None:
        _raw_prompt = _PROMPT_PATH.read_text(encoding="utf-8")
    return _raw_prompt


def build_system_prompt(
    *,
    nome_usuario: str = "",
    telefone: str = "",
    data_atual: str,
    dica_rag: str = "",
) -> str:
    """Renderiza o system prompt de cadastro."""
    raw = _load_raw()
    return (
        raw
        .replace("{{data_atual}}", data_atual)
        .replace("{{nome_usuario}}", nome_usuario)
        .replace("{{telefone}}", telefone)
        .replace("{{dica_rag}}", dica_rag)
    )
