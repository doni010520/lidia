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
        assert rota.suppress_tools == ["oracao_do_dia"]
        assert rota.tools_called == ["oracao_do_dia"]
        assert "JÁ FOI ENVIADO" in rota.system_note
        envio.assert_awaited_once_with("5581999")

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
