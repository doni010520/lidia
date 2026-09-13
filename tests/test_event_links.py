"""Link de evento só sai se veio da Diacon (ou da própria pessoa) neste turno.

Incidente 13/09 (Tercia, 558196157879): perguntou como se inscrever na
Imersão de Oração e recebeu o link da Conferência 30 Anos — evento encerrado
em 22/08. O modelo não chamou `buscar_evento` (log `iter=0`) e copiou a
"Dica de resposta", que vinha de ~30 linhas vencidas da planilha. O mesmo
aconteceu em 30/08. Instrução no prompt não segurou; a trava é em código.
"""
from __future__ import annotations

import pytest

from app.services.event_links import (
    links_nao_verificados,
    responder_com_links_verificados,
    strip_event_links,
)

CONF_30 = "https://diacon.ia.br/e/conf-30-anos-paes-08-20"
IMERSAO_ORACAO = "https://diacon.ia.br/e/imersao-ceus-abertos"

# Texto real que a LidIA mandou para a Tercia (vinha da planilha)
RESPOSTA_TERCIA = (
    "As inscrições para a Conferência PAES 30 Anos | LEGADO estão abertas e são "
    f"feitas pelo site: {CONF_30}\n\nÉ só abrir o link, preencher seus dados e "
    "concluir o pagamento. Se precisar de ajuda, fale com a Secretaria: "
    "https://wa.me/558196920063"
)

TOOL_IMERSAO = (
    "Encontrados 1 evento(s):\n\n📌 Imersão de Oração - Frutificando no Secreto | "
    f"Data: 18/09/2026 a 19/09/2026 | Inscrição: aberta | Link: {IMERSAO_ORACAO}"
)

TOOLS = [
    {"type": "function", "function": {"name": "buscar_evento"}},
    {"type": "function", "function": {"name": "oracao_do_dia"}},
]

FORCA_BUSCAR_EVENTO = {"type": "function", "function": {"name": "buscar_evento"}}


# ── 1. Remover link de evento de texto que não é da Diacon ──

class TestStripEventLinks:
    def test_remove_link_diacon_de_evento(self):
        out = strip_event_links(RESPOSTA_TERCIA)
        assert "diacon.ia.br/e/" not in out
        assert "Conferência PAES 30 Anos" in out  # o assunto continua

    def test_remove_link_somospaes(self):
        texto = "LINK: https://somospaes.com.br/Somos%20PAES/happening-brasil-35-hb35/inscricoes"
        assert "somospaes.com.br" not in strip_event_links(texto)

    def test_preserva_links_que_nao_sao_de_evento(self):
        texto = (
            "Secretaria: https://wa.me/558196920063 | "
            "comprovante: https://diacon.ia.br/minha-inscricao/paes-catedral"
        )
        assert strip_event_links(texto) == texto


# ── 2. Quais links da resposta não têm origem no turno ──

class TestLinksNaoVerificados:
    def test_link_sem_origem_e_apontado(self):
        assert links_nao_verificados(RESPOSTA_TERCIA, ["Como me inscrever?"]) == [CONF_30]

    def test_link_que_veio_da_ferramenta_passa(self):
        resposta = f"Inscreva-se aqui: {IMERSAO_ORACAO}"
        assert links_nao_verificados(resposta, [TOOL_IMERSAO]) == []

    def test_link_que_a_pessoa_mandou_passa(self):
        # 14:29 — a Tercia encaminhou o panfleto com o link certo
        panfleto = f"Dias 18 e 19/09 teremos o nosso Imersão de Oração. Se inscreva pelo link:\n{IMERSAO_ORACAO}"
        resposta = f"Pode usar este link: {IMERSAO_ORACAO}"
        assert links_nao_verificados(resposta, [panfleto]) == []

    def test_slug_parecido_nao_passa(self):
        # Diacon tem imersao-ceus-abertos E imersao-ceus-abertos-09-18: prefixo não vale
        resposta = f"Link: {IMERSAO_ORACAO}-09-18"
        assert links_nao_verificados(resposta, [TOOL_IMERSAO]) == [f"{IMERSAO_ORACAO}-09-18"]

    def test_markdown_pontuacao_e_sem_https_sao_normalizados(self):
        resposta = f"🔗 [Inscrição]({IMERSAO_ORACAO}). Ou diacon.ia.br/e/imersao-ceus-abertos/."
        assert links_nao_verificados(resposta, [TOOL_IMERSAO]) == []

    def test_resposta_sem_link_de_evento(self):
        assert links_nao_verificados("Fale com a Secretaria: https://wa.me/558196920063", []) == []


# ── 3. A trava em volta do chat ──

class FakeOAI:
    """Roteiro de respostas do modelo. Cada passo: {'tool': resultado|None, 'reply': texto}."""

    def __init__(self, roteiro: list[dict]):
        self.roteiro = list(roteiro)
        self.calls: list[dict] = []

    async def chat(self, *, messages, system_prompt, tools, phone, tool_handler, tool_choice=None):
        self.calls.append({"system_prompt": system_prompt, "tool_choice": tool_choice, "tools": tools})
        passo = self.roteiro.pop(0)
        called: list[str] = []
        if passo.get("tool") is not None:
            messages.append({
                "role": "assistant", "content": "",
                "tool_calls": [{"id": "c1", "type": "function",
                                "function": {"name": "buscar_evento", "arguments": "{}"}}],
            })
            messages.append({"role": "tool", "tool_call_id": "c1", "content": passo["tool"]})
            called = ["buscar_evento"]
        messages.append({"role": "assistant", "content": passo["reply"]})
        return passo["reply"], messages, called


def _historico_tercia() -> list[dict]:
    return [
        {"role": "user", "content": "[15/07] Sim ! O link da Conferência dos 30 anos da Paes !"},
        {"role": "assistant", "content": f"[15/07] Você pode se inscrever pelo link: {CONF_30}"},
        {"role": "user", "content": "Como me inscrever?"},
    ]


class TestResponderComLinksVerificados:
    @pytest.mark.asyncio
    async def test_caso_tercia_resposta_com_link_da_planilha_forca_buscar_evento(self):
        oai = FakeOAI([
            {"tool": None, "reply": RESPOSTA_TERCIA},
            {"tool": TOOL_IMERSAO, "reply": f"Inscreva-se na Imersão de Oração: {IMERSAO_ORACAO}"},
        ])
        hist = _historico_tercia()

        reply, hist_out, called = await responder_com_links_verificados(
            oai, history=hist, system_prompt="SYS", tools=TOOLS, phone="558196157879",
            tool_handler=None, fontes_do_turno=["Como me inscrever?"],
        )

        assert len(oai.calls) == 2
        assert oai.calls[0]["tool_choice"] is None
        assert oai.calls[1]["tool_choice"] == FORCA_BUSCAR_EVENTO
        assert oai.calls[1]["system_prompt"].startswith("SYS")
        assert "buscar_evento" in oai.calls[1]["system_prompt"][len("SYS"):]
        assert IMERSAO_ORACAO in reply
        assert CONF_30 not in reply
        assert called == ["buscar_evento"]
        # a resposta rejeitada não fica no histórico (senão seria salva e relida)
        assert all(RESPOSTA_TERCIA != m.get("content") for m in hist_out)
        assert hist_out[-1] == {"role": "assistant", "content": reply}

    @pytest.mark.asyncio
    async def test_link_que_veio_da_ferramenta_nao_repete_chamada(self):
        oai = FakeOAI([{"tool": TOOL_IMERSAO, "reply": f"Link: {IMERSAO_ORACAO}"}])
        reply, _, called = await responder_com_links_verificados(
            oai, history=[{"role": "user", "content": "link da imersão"}], system_prompt="SYS",
            tools=TOOLS, phone="5581", tool_handler=None, fontes_do_turno=["link da imersão"],
        )
        assert len(oai.calls) == 1
        assert reply == f"Link: {IMERSAO_ORACAO}"
        assert called == ["buscar_evento"]

    @pytest.mark.asyncio
    async def test_link_que_a_pessoa_mandou_nao_repete_chamada(self):
        panfleto = f"Se inscreva pelo link:\n{IMERSAO_ORACAO}"
        oai = FakeOAI([{"tool": None, "reply": f"Pode usar este link: {IMERSAO_ORACAO}"}])
        await responder_com_links_verificados(
            oai, history=[{"role": "user", "content": panfleto}], system_prompt="SYS",
            tools=TOOLS, phone="5581", tool_handler=None, fontes_do_turno=[panfleto],
        )
        assert len(oai.calls) == 1

    @pytest.mark.asyncio
    async def test_se_insistir_sem_origem_o_link_e_retirado(self):
        oai = FakeOAI([
            {"tool": None, "reply": RESPOSTA_TERCIA},
            {"tool": None, "reply": RESPOSTA_TERCIA},
        ])
        reply, hist_out, _ = await responder_com_links_verificados(
            oai, history=_historico_tercia(), system_prompt="SYS", tools=TOOLS,
            phone="5581", tool_handler=None, fontes_do_turno=["Como me inscrever?"],
        )
        assert len(oai.calls) == 2
        assert "diacon.ia.br/e/" not in reply
        assert "wa.me/558196920063" in reply
        assert hist_out[-1] == {"role": "assistant", "content": reply}

    @pytest.mark.asyncio
    async def test_sem_buscar_evento_disponivel_retira_o_link_sem_nova_chamada(self):
        oai = FakeOAI([{"tool": None, "reply": RESPOSTA_TERCIA}])
        reply, _, _ = await responder_com_links_verificados(
            oai, history=_historico_tercia(), system_prompt="SYS",
            tools=[{"type": "function", "function": {"name": "cadastrar_contato"}}],
            phone="5581", tool_handler=None, fontes_do_turno=["Como me inscrever?"],
        )
        assert len(oai.calls) == 1
        assert "diacon.ia.br/e/" not in reply
