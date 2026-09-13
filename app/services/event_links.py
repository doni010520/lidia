"""Link de evento só sai para a pessoa se veio da Diacon neste turno.

Incidente 13/09 (Tercia): "Como me inscrever?" sobre a Imersão de Oração
recebeu o link da Conferência 30 Anos, encerrada em 22/08. O modelo não chamou
`buscar_evento` e copiou a "Dica de resposta" — ~30 linhas vencidas da
planilha de informações. Já tinha acontecido em 30/08, e o prompt já mandava
chamar a ferramenta para "inscrição" e "evento". Instrução no prompt é pedido;
esta trava é garantia.

Regra: todo link de evento na resposta precisa ter aparecido num resultado de
ferramenta deste turno ou na mensagem da própria pessoa (panfleto encaminhado).
Se não apareceu, a resposta é refeita com `buscar_evento` forçado; se ainda
assim o link não tiver origem, ele é retirado antes do envio.
"""
from __future__ import annotations

import re
from typing import Any

from loguru import logger

# diacon.ia.br/e/<slug> = página/inscrição de evento na Diacon.
# somospaes.com.br = inscrições da era do n8n (Happening, Cursilho), hoje só em texto velho.
# minha-inscricao (autoatendimento) e wa.me não são link de evento e ficam de fora.
_EVENT_LINK_RE = re.compile(
    r"(?:https?://)?(?:www\.)?"
    r"(?:diacon\.ia\.br/e/[^\s)\]>*,|\"'<]+|somospaes\.com\.br(?:/[^\s)\]>*,|\"'<]*)?)",
    re.IGNORECASE,
)
_PONTUACAO_FINAL = ".;:!?"

FORCAR_BUSCAR_EVENTO = {"type": "function", "function": {"name": "buscar_evento"}}

_NOTA_VERIFICACAO = (
    "\n\n---\n\n"
    "[VERIFICAÇÃO DE LINK] Sua resposta anterior trazia link de evento que NÃO saiu da "
    "agenda da Diacon neste turno: {links}. Esse link veio de texto antigo (dica ou "
    "histórico) e pode ser de outro evento ou de um evento que já acabou. Link de evento "
    "ou de inscrição só pode ser copiado do resultado de `buscar_evento`. Chame "
    "`buscar_evento` agora, com o nome do evento que a pessoa quer, e responda somente "
    "com o que a ferramenta devolver. Se a agenda não trouxer o evento, diga isso e "
    "ofereça a Secretaria."
)


def _limpar(url: str) -> str:
    return url.rstrip(_PONTUACAO_FINAL)


def _chave(url: str) -> str:
    """Forma comparável: sem esquema, sem www, sem barra final, minúscula."""
    u = _limpar(url).lower()
    u = re.sub(r"^https?://", "", u)
    u = re.sub(r"^www\.", "", u)
    return u.rstrip("/")


def _encontrar(texto: str | None) -> list[str]:
    return [_limpar(m.group(0)) for m in _EVENT_LINK_RE.finditer(texto or "")]


def _retirar(texto: str, chaves: set[str] | None = None) -> str:
    """Remove links de evento (todos, ou só os de `chaves`), preservando a pontuação final."""
    def _sub(m: re.Match) -> str:
        url = m.group(0)
        if chaves is not None and _chave(url) not in chaves:
            return url
        return url[len(_limpar(url)):]

    return _EVENT_LINK_RE.sub(_sub, texto)


def strip_event_links(texto: str) -> str:
    """Tira link de evento de texto que não é da Diacon (dica do RAG, fallback)."""
    return _retirar(texto)


def links_nao_verificados(resposta: str, fontes: list[str]) -> list[str]:
    """Links de evento da resposta que não aparecem em nenhuma das fontes."""
    permitidas = {_chave(u) for fonte in fontes for u in _encontrar(fonte)}
    suspeitos: list[str] = []
    vistos: set[str] = set()
    for url in _encontrar(resposta):
        chave = _chave(url)
        if chave not in permitidas and chave not in vistos:
            suspeitos.append(url)
            vistos.add(chave)
    return suspeitos


def _resultados_de_ferramenta(entradas: list[dict[str, Any]]) -> list[str]:
    return [str(e.get("content") or "") for e in entradas if e.get("role") == "tool"]


def _ultima_e_resposta(history: list[dict[str, Any]], reply: str) -> bool:
    if not history:
        return False
    ultima = history[-1]
    return (
        ultima.get("role") == "assistant"
        and not ultima.get("tool_calls")
        and ultima.get("content") == reply
    )


async def responder_com_links_verificados(
    oai: Any,
    *,
    history: list[dict[str, Any]],
    system_prompt: str,
    tools: list[dict] | None,
    phone: str,
    tool_handler: Any,
    fontes_do_turno: list[str],
) -> tuple[str, list[dict[str, Any]], list[str]]:
    """`oai.chat` com a trava de links. Mesmo retorno de `OpenAIService.chat`."""
    log = logger.bind(phone=phone)
    inicio = len(history)

    reply, history, tools_called = await oai.chat(
        messages=history, system_prompt=system_prompt, tools=tools,
        phone=phone, tool_handler=tool_handler,
    )
    suspeitos = links_nao_verificados(
        reply, [*fontes_do_turno, *_resultados_de_ferramenta(history[inicio:])],
    )
    if not suspeitos:
        return reply, history, tools_called

    tem_buscar_evento = any(
        (t.get("function") or {}).get("name") == "buscar_evento" for t in (tools or [])
    )
    if tem_buscar_evento:
        log.warning(f"Trava de links: link de evento sem origem no turno {suspeitos} — refazendo com buscar_evento")
        # A resposta rejeitada sai do histórico: não é enviada, não é salva, não é relida.
        if _ultima_e_resposta(history, reply):
            history.pop()
        reply, history, mais_tools = await oai.chat(
            messages=history,
            system_prompt=system_prompt + _NOTA_VERIFICACAO.format(links=", ".join(suspeitos)),
            tools=tools, phone=phone, tool_handler=tool_handler,
            tool_choice=FORCAR_BUSCAR_EVENTO,
        )
        tools_called = tools_called + mais_tools
        suspeitos = links_nao_verificados(
            reply, [*fontes_do_turno, *_resultados_de_ferramenta(history[inicio:])],
        )
        if not suspeitos:
            return reply, history, tools_called

    log.error(f"Trava de links: retirando da resposta links de evento sem origem {suspeitos}")
    limpa = _retirar(reply, {_chave(u) for u in suspeitos})
    if _ultima_e_resposta(history, reply):
        history[-1] = {"role": "assistant", "content": limpa}
    return limpa, history, tools_called
