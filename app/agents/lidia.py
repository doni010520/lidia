"""Agente principal LidIA — atende leads já cadastrados.

Fase 3: 5 tools de atendimento/CRM. Fases futuras adicionarão
buscar_evento, plano_de_leitura, notificar, etc.
"""
from __future__ import annotations

from pathlib import Path

from app.tools.registry import get_tools

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "lidia_system.txt"
_raw_prompt: str | None = None

TOOLS_ALLOWED: list[str] = [
    "buscar_documentos",
    "buscar_evento",
    "plano_de_leitura",
    "cadastrar_contato",
    "cadastrar_aniversario",
    "atualizar_sobrenome",
    "excluir_usuario",
    "novos_convertidos",
    "PAES_listar_arquivos",
    "PAES_download_arquivos",
    "encaminhar_video_louvor",
    "notificar_time_interno",
    "resposta_oracao",
]
tools_allowed: list[dict] = get_tools(TOOLS_ALLOWED)

# Tools administrativas — disponíveis somente via painel (não expostas ao agente)
ADMIN_TOOLS: list[str] = [
    "eventos_Lidia",
    "informacoes_Lidia",
    "treinamento_LidIA",
]
admin_tools_allowed: list[dict] = get_tools(ADMIN_TOOLS)


def _load_raw() -> str:
    global _raw_prompt
    if _raw_prompt is None:
        _raw_prompt = _PROMPT_PATH.read_text(encoding="utf-8")
    return _raw_prompt


def build_system_prompt(
    *,
    nome_usuario: str,
    telefone: str,
    data_atual: str,
    dica_rag: str,
) -> str:
    """Renderiza o system prompt com str.replace nos 4 placeholders.

    Usa str.replace porque o prompt de 75KB contém $, %, { e } literais
    que Jinja2 interpretaria como expressões.
    """
    raw = _load_raw()
    return (
        raw
        .replace("{{data_atual}}", data_atual)
        .replace("{{nome_usuario}}", nome_usuario)
        .replace("{{telefone}}", telefone)
        .replace("{{dica_rag}}", dica_rag)
    )
