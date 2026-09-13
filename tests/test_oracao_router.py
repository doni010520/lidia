"""Testes do pré-roteador de oração.

Cobre as três regressões que apareceram em produção:

1. "link de oração" caía na Alvorada (RAG vencia a ferramenta);
2. pedido específico ainda levava pergunta de desambiguação (turno extra);
3. o mural chegava DUPLICADO — o roteador executava a tool e o LLM chamava
   de novo, gerando dois links autenticados distintos.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import settings
from app.services.oracao_router import OracaoRoute, detect, resolve


# ── 1. Detecção de intenção ──

class TestDetect:
    @pytest.mark.parametrize("texto", [
        "link de oração",
        "Link de oração do mural",          # frase exata do relato original
        "link da oracao",
        "me manda o link de oração",
        "link do mural",
        "quero orar com a igreja",
        "qual a oração de hoje?",
        "manda a oração",
        "qual o tema de oração de hoje",
        "quero registrar minha oração",
    ])
    def test_pedido_de_link_vai_para_o_mural(self, texto):
        """Nunca pode devolver 'alvorada': é a regressão que gerou o relato."""
        assert detect(texto) == "mural"

    @pytest.mark.parametrize("texto", [
        "link da alvorada",
        "qual o link da alvorada de oração",
        "que horas é a Alvorada?",
        "ALVORADA FEMININA",
    ])
    def test_alvorada_so_quando_citada(self, texto):
        assert detect(texto) == "alvorada"

    @pytest.mark.parametrize("texto", [
        "orem por mim",
        "preciso de oração",
        "minha mãe está doente, ora por mim",
        "quero fazer um pedido de oração",
        "preciso de intercessão pela minha família",
    ])
    def test_pedido_pessoal_nao_e_roteado(self, texto):
        """Sai do roteador para o LLM chamar `pedido_oracao`."""
        assert detect(texto) is None

    @pytest.mark.parametrize("texto", [
        "",
        "   ",
        "bom dia!",
        "quando é o próximo culto?",
        "[SISTEMA] Usuário enviou vídeo. drive_file_id: abc",
        "[LOCALIZAÇÃO] O usuário compartilhou sua localização: lat=1, lng=2",
    ])
    def test_fora_do_escopo(self, texto):
        assert detect(texto) is None

    @pytest.mark.parametrize("texto", [
        "Calendário de oração",
        "Quero o link do calendário de oração",
        "Calendário de oração diário",
        "Oração diária",
        "Link de oração diária",
    ])
    def test_como_as_pessoas_pedem_o_mural_de_verdade(self, texto):
        """Fraseados reais, colhidos das conversas de produção."""
        assert detect(texto) == "mural"

    def test_acento_e_caixa_nao_importam(self):
        assert detect("LINK DE ORAÇÃO") == detect("link de oracao") == "mural"


# ── 2. Resolução do mural ──

class TestResolveMural:
    @pytest.mark.asyncio
    async def test_sucesso_suprime_a_tool(self):
        """A causa da duplicação: sem isso o LLM chama `oracao_do_dia` de novo."""
        envio = AsyncMock(return_value=(True, "Mural enviado."))
        with patch("app.tools.tool_modules.oracao_do_dia.enviar", envio):
            rota = await resolve("link de oração", "5581999", AsyncMock())

        assert rota.handled is True
        assert rota.suppress_tools == ["oracao_do_dia", "notificar_time_interno"]
        assert rota.tools_called == ["oracao_do_dia"]
        assert "JÁ FOI ENVIADO" in rota.system_note
        envio.assert_awaited_once_with("5581999")

    @pytest.mark.asyncio
    async def test_sucesso_suprime_o_encaminhamento_para_a_equipe(self):
        """O bug de 09/09: mural entregue e, no mesmo turno, "já encaminhei
        sua solicitação para a equipe de oração para que enviem o link".

        O modelo não acha `oracao_do_dia` na lista (suprimida por já ter
        rodado em código) e cai na regra genérica do prompt "não consegui →
        `notificar_time_interno`". A pessoa recebe o link e ouve que não tem,
        e a equipe de Oração recebe um chamado falso a cada pedido de mural.
        """
        envio = AsyncMock(return_value=(True, "Mural enviado."))
        with patch("app.tools.tool_modules.oracao_do_dia.enviar", envio):
            rota = await resolve("Quero o link do calendário de oração", "5581999", AsyncMock())

        assert "notificar_time_interno" in rota.suppress_tools
        assert "notificar_time_interno" in rota.system_note

    @pytest.mark.asyncio
    async def test_nao_membro_nao_afirma_que_enviou(self):
        """`enviar` devolve ok=False sem exceção — o note não pode mentir."""
        envio = AsyncMock(return_value=(False, "A pessoa ainda não está cadastrada como membro."))
        with patch("app.tools.tool_modules.oracao_do_dia.enviar", envio):
            rota = await resolve("link de oração", "5581999", AsyncMock())

        assert rota.handled is True
        assert "NÃO recebeu nada" in rota.system_note
        assert "JÁ FOI ENVIADO" not in rota.system_note
        # Falhou: a tool continua disponível para o LLM tentar de novo.
        assert rota.suppress_tools == []

    @pytest.mark.asyncio
    async def test_excecao_inesperada_nao_derruba_o_turno(self):
        envio = AsyncMock(side_effect=RuntimeError("boom"))
        with patch("app.tools.tool_modules.oracao_do_dia.enviar", envio):
            rota = await resolve("link de oração", "5581999", AsyncMock())

        assert rota.handled is True
        assert rota.suppress_tools == []
        assert "NÃO recebeu nada" in rota.system_note

    @pytest.mark.asyncio
    async def test_pedido_pessoal_nao_dispara_a_ferramenta(self):
        envio = AsyncMock()
        with patch("app.tools.tool_modules.oracao_do_dia.enviar", envio):
            rota = await resolve("orem por mim", "5581999", AsyncMock())

        assert rota.handled is False
        envio.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_desligado_por_config_nao_roteia(self):
        envio = AsyncMock()
        with (
            patch("app.services.oracao_router.settings.oracao_router_enabled", False),
            patch("app.tools.tool_modules.oracao_do_dia.enviar", envio),
        ):
            rota = await resolve("link de oração", "5581999", AsyncMock())

        assert rota.handled is False
        envio.assert_not_awaited()


# ── 3. Resolução da Alvorada ──

class TestResolveAlvorada:
    @pytest.mark.asyncio
    async def test_entrega_os_links_configurados(self):
        with (
            patch("app.services.oracao_router.settings.alvorada_oracao_link", "https://meet.example/abc"),
            patch("app.services.oracao_router.settings.alvorada_feminina_link", ""),
            patch("app.services.oracao_router.settings.alvorada_homens_link", ""),
        ):
            rota = await resolve("link da alvorada", "5581999", AsyncMock())

        assert rota.handled is True
        assert "https://meet.example/abc" in rota.system_note
        assert rota.tools_called == []

    @pytest.mark.asyncio
    async def test_sem_link_configurado_nao_assume_o_turno(self):
        """Comportamento atual, documentado: cai no RAG.

        Enquanto as env vars ALVORADA_*_LINK estiverem vazias, a busca vetorial
        responde — e pode devolver o link desatualizado da planilha. Ponto em
        aberto, registrado aqui de propósito.
        """
        with (
            patch("app.services.oracao_router.settings.alvorada_oracao_link", ""),
            patch("app.services.oracao_router.settings.alvorada_feminina_link", ""),
            patch("app.services.oracao_router.settings.alvorada_homens_link", ""),
        ):
            rota = await resolve("link da alvorada", "5581999", AsyncMock())

        assert rota.handled is False


# ── 4. Contrato do dataclass ──

def test_rota_vazia_e_inerte():
    rota = OracaoRoute()
    assert (rota.handled, rota.system_note, rota.tools_called, rota.suppress_tools) == (False, "", [], [])


# ── 4. Registro na história (a LidIA precisa saber o que ELA fez) ──

class TestTranscricaoDoQueFoiExecutado:
    """O roteador agia e não deixava rastro.

    O envio do mural acontecia em código, fora do loop de tools, e por isso
    nunca era gravado em `lidia.messages`. No turno seguinte o histórico
    mostrava o pedido da pessoa e a resposta da LidIA — e nenhuma linha
    dizendo que o mural tinha saído. Em 31/08 e 04/09 a mesma pessoa pediu o
    link duas vezes; nas duas o mural foi enviado, e na segunda a LidIA
    respondeu "encaminhei NOVAMENTE seu pedido", lendo o próprio
    encaminhamento anterior e sem enxergar as duas entregas.

    A transcrição devolve ao histórico o formato que o loop de tools já usa,
    de modo que um turno resolvido em código fique indistinguível de um
    turno resolvido pelo LLM.
    """

    @pytest.mark.asyncio
    async def test_sucesso_gera_par_assistant_tool(self):
        envio = AsyncMock(return_value=(True, "Mural enviado."))
        with patch("app.tools.tool_modules.oracao_do_dia.enviar", envio):
            rota = await resolve("link de oração", "5581999", AsyncMock())

        chamada, resultado = rota.transcript

        assert chamada["role"] == "assistant"
        assert chamada["tool_calls"][0]["function"]["name"] == "oracao_do_dia"
        assert "5581999" in chamada["tool_calls"][0]["function"]["arguments"]

        assert resultado["role"] == "tool"
        assert resultado["name"] == "oracao_do_dia"
        assert resultado["content"] == "Mural enviado."
        # O par precisa casar, senão a OpenAI rejeita o histórico.
        assert resultado["tool_call_id"] == chamada["tool_calls"][0]["id"]

    @pytest.mark.asyncio
    async def test_falha_tambem_fica_registrada(self):
        """Tentativa que não entregou também é história — e evita que o
        turno seguinte comece do zero achando que nada foi tentado."""
        envio = AsyncMock(return_value=(False, "A pessoa não é membro."))
        with patch("app.tools.tool_modules.oracao_do_dia.enviar", envio):
            rota = await resolve("link de oração", "5581999", AsyncMock())

        chamada, resultado = rota.transcript
        assert chamada["tool_calls"][0]["function"]["name"] == "oracao_do_dia"
        assert resultado["content"] == "A pessoa não é membro."

    @pytest.mark.asyncio
    async def test_alvorada_nao_executou_nada_entao_nao_transcreve(self):
        """A rota da Alvorada só injeta dados no prompt — não envia nada,
        então não há execução para registrar."""
        with patch.object(settings, "alvorada_oracao_link", "https://x/alvorada"):
            rota = await resolve("link da alvorada", "5581999", AsyncMock())

        assert rota.handled is True
        assert rota.transcript == []

    @pytest.mark.asyncio
    async def test_ids_nao_se_repetem_entre_turnos(self):
        envio = AsyncMock(return_value=(True, "Mural enviado."))
        with patch("app.tools.tool_modules.oracao_do_dia.enviar", envio):
            a = await resolve("link de oração", "5581999", AsyncMock())
            b = await resolve("link de oração", "5581999", AsyncMock())

        assert a.transcript[1]["tool_call_id"] != b.transcript[1]["tool_call_id"]


# ── 5. O par transcrito sobrevive à volta pelo histórico ──

class TestTranscricaoVoltaDoHistorico:
    """O histórico é reconstruído do banco a cada turno e passa por uma
    sanitização (a OpenAI rejeita `tool` órfão e `assistant` com `tool_calls`
    sem resposta). Se o par gravado pelo roteador não sobrevivesse a ela, o
    registro existiria no banco e mesmo assim não chegaria ao modelo — que é
    o problema que essa transcrição existe para resolver.
    """

    @staticmethod
    def _linhas(transcript):
        """Simula as linhas de `lidia.messages` gravadas pelo passo 7b."""
        from datetime import datetime
        from unittest.mock import MagicMock
        from zoneinfo import ZoneInfo

        agora = datetime(2026, 9, 10, 12, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
        linhas = [MagicMock(role="user", content="Quero o link do calendário de oração",
                            tool_call_id=None, tool_name=None, tool_calls_json=None,
                            created_at=agora)]
        for e in transcript:
            linhas.append(MagicMock(
                role=e["role"], content=e.get("content", ""),
                tool_call_id=e.get("tool_call_id"), tool_name=e.get("name"),
                tool_calls_json=e.get("tool_calls"), created_at=agora,
            ))
        return linhas

    async def _carregar(self, linhas):
        from unittest.mock import AsyncMock, MagicMock
        from app.services.conversation_service import load_history

        resultado = MagicMock()
        resultado.scalars.return_value.all.return_value = list(reversed(linhas))
        db = AsyncMock()
        db.execute.return_value = resultado
        return await load_history(db, "5581999")

    @pytest.mark.asyncio
    async def test_par_completo_chega_ao_modelo(self):
        envio = AsyncMock(return_value=(True, "Mural enviado."))
        with patch("app.tools.tool_modules.oracao_do_dia.enviar", envio):
            rota = await resolve("link de oração", "5581999", AsyncMock())

        hist = await self._carregar(self._linhas(rota.transcript))

        assert [e["role"] for e in hist] == ["user", "assistant", "tool"]
        assert hist[2]["content"].endswith("Mural enviado.")

    @pytest.mark.asyncio
    async def test_janela_cortada_no_meio_do_par_nao_quebra_a_openai(self):
        """`history_limit` pode cortar entre o assistant e o tool. O tool
        órfão precisa cair fora — senão a API rejeita o turno inteiro."""
        envio = AsyncMock(return_value=(True, "Mural enviado."))
        with patch("app.tools.tool_modules.oracao_do_dia.enviar", envio):
            rota = await resolve("link de oração", "5581999", AsyncMock())

        linhas = self._linhas(rota.transcript)
        hist = await self._carregar(linhas[2:])  # perdeu o assistant com tool_calls

        assert [e["role"] for e in hist] == []
