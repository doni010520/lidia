"""Dispatcher central de tools.

Roteia chamadas por nome da tool para o módulo correspondente.
Injeção de dependências: cada handler recebe (args, phone, db).

Convenção de persistência por tool:
- Mutação simples (UPDATE campo) → await db.flush()
  O commit final acontece no pipeline (conversation_service passo 13).
  Exemplos: cadastrar_aniversario, atualizar_sobrenome, cadastrar_contato (update).
- Operação destrutiva ou criação isolada → await db.commit()
  Garante atomicidade independente do pipeline.
  Exemplos: excluir_usuario (DELETE cascade), cadastrar_contato (INSERT novo).
"""
from __future__ import annotations

from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.tools.tool_modules import (
    atualizar_sobrenome,
    buscar_documentos,
    buscar_evento,
    cadastrar_aniversario,
    cadastrar_contato,
    celulas_proximas,
    encaminhar_video_louvor,
    eventos_lidia,
    excluir_usuario,
    informacoes_lidia,
    link_foto_perfil,
    minha_caminhada,
    notificar_time_interno,
    novos_convertidos,
    oracao_do_dia,
    paes_download_arquivos,
    paes_listar_arquivos,
    panorama_igreja,
    pedido_oracao,
    plano_de_leitura,
    qr_celula,
    resposta_oracao,
    resumo_celula,
    treinamento_lidia,
)

# Mapa de tools registradas
_HANDLERS: dict[str, Any] = {
    "buscar_documentos": buscar_documentos,
    "buscar_evento": buscar_evento,
    "plano_de_leitura": plano_de_leitura,
    "cadastrar_contato": cadastrar_contato,
    "cadastrar_aniversario": cadastrar_aniversario,
    "atualizar_sobrenome": atualizar_sobrenome,
    "excluir_usuario": excluir_usuario,
    "novos_convertidos": novos_convertidos,
    "PAES_listar_arquivos": paes_listar_arquivos,
    "PAES_download_arquivos": paes_download_arquivos,
    "encaminhar_video_louvor": encaminhar_video_louvor,
    "notificar_time_interno": notificar_time_interno,
    "resposta_oracao": resposta_oracao,
    "eventos_Lidia": eventos_lidia,
    "informacoes_Lidia": informacoes_lidia,
    "treinamento_LidIA": treinamento_lidia,
    # ── Diacon (Fase 1A) ──
    "oracao_do_dia": oracao_do_dia,
    "pedido_oracao": pedido_oracao,
    "link_foto_perfil": link_foto_perfil,
    "qr_celula": qr_celula,
    "celulas_proximas": celulas_proximas,
    "minha_caminhada": minha_caminhada,
    "panorama_igreja": panorama_igreja,
    "resumo_celula": resumo_celula,
}


async def handle_tool_call(
    tool_name: str,
    args: dict,
    phone: str,
    *,
    db: AsyncSession | None = None,
) -> str:
    """Despacha chamada de tool para o handler correto.

    Args:
        tool_name: nome da function chamada pelo LLM
        args: argumentos parseados do function call
        phone: telefone do contato (contexto)
        db: sessão do banco (injetada pelo pipeline)

    Returns:
        String com resultado da tool (para o LLM continuar)
    """
    handler = _HANDLERS.get(tool_name)
    if handler is None:
        logger.warning(f"Tool desconhecida: {tool_name}")
        return f"Erro: tool '{tool_name}' não encontrada."

    try:
        result = await handler.execute(args, phone, db)
        logger.bind(phone=phone).info(f"Tool {tool_name} → OK")
        return result
    except Exception as exc:
        logger.bind(phone=phone).exception(f"Erro na tool {tool_name}")
        return f"Erro ao executar {tool_name}: {str(exc)}"
