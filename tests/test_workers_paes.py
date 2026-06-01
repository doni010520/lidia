"""Testes para os 4 workers PAES portados do n8n."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# === aniversarios ===

class TestAniversarios:
    @pytest.mark.asyncio
    async def test_sem_aniversariantes_retorna_zero(self):
        from app.workers import aniversarios
        with patch.object(aniversarios, "_fetch_aniversariantes", new_callable=AsyncMock) as mock:
            mock.return_value = []
            result = await aniversarios.check_aniversariantes()
            assert result == {"aniversariantes": 0, "mensagens_enviadas": 0, "pastores_avisados": 0}

    @pytest.mark.asyncio
    async def test_envia_para_aniversariantes_e_pastores(self):
        from app.workers import aniversarios

        aniversariantes_mock = [
            {"id": 1, "telefone": "5581999999999", "nome": "Joao", "email": "j@x.com"},
        ]
        pastores_mock = [{"id": 1, "nome": "Pastor Carlos", "telefone": "5581888888888"}]
        mock_uaz = MagicMock()
        mock_uaz.send_text = AsyncMock(return_value={"ok": True})

        with (
            patch.object(aniversarios, "_fetch_aniversariantes", new_callable=AsyncMock) as ma,
            patch.object(aniversarios, "_fetch_pastores", new_callable=AsyncMock) as mp,
            patch.object(aniversarios, "get_uaz_client", return_value=mock_uaz),
            patch.object(aniversarios, "_gerar_mensagem_individual", new_callable=AsyncMock) as mmsg,
            patch.object(aniversarios, "_gerar_relatorio_pastores", new_callable=AsyncMock) as mrel,
            patch.object(aniversarios.asyncio, "sleep", new_callable=AsyncMock),
        ):
            ma.return_value = aniversariantes_mock
            mp.return_value = pastores_mock
            mmsg.return_value = "Parabens!"
            mrel.return_value = "Relatorio do dia"
            result = await aniversarios.check_aniversariantes()

        assert result["aniversariantes"] == 1
        assert result["mensagens_enviadas"] == 1
        assert result["pastores_avisados"] == 1
        assert mock_uaz.send_text.await_count == 2


# === disparo_liderancas ===

class TestDisparoLiderancas:
    @pytest.mark.asyncio
    async def test_sem_liderancas(self):
        from app.workers import disparo_liderancas
        with patch.object(disparo_liderancas, "_fetch_liderancas", new_callable=AsyncMock) as m:
            m.return_value = []
            r = await disparo_liderancas.disparar_liderancas()
            assert r == {"liderancas": 0, "enviadas": 0, "falhas": 0}

    @pytest.mark.asyncio
    async def test_envia_para_cada_lider(self):
        from app.workers import disparo_liderancas
        lideres = [
            {"id": 1, "nome": "Ana", "telefone": "5581111", "ministerio": "Louvor"},
            {"id": 2, "nome": "Bruno", "telefone": "5581222", "ministerio": "Cursilho"},
        ]
        mock_uaz = MagicMock()
        mock_uaz.send_text = AsyncMock()
        with (
            patch.object(disparo_liderancas, "_fetch_liderancas", new_callable=AsyncMock) as ml,
            patch.object(disparo_liderancas, "get_uaz_client", return_value=mock_uaz),
            patch.object(disparo_liderancas, "_gerar_mensagem", new_callable=AsyncMock) as mmsg,
            patch.object(disparo_liderancas.asyncio, "sleep", new_callable=AsyncMock),
        ):
            ml.return_value = lideres
            mmsg.return_value = "Ola lider"
            r = await disparo_liderancas.disparar_liderancas()
        assert r["liderancas"] == 2
        assert r["enviadas"] == 2


# === boas_vindas_convertidos ===

class TestBoasVindasConvertidos:
    @pytest.mark.asyncio
    async def test_sem_convertidos(self):
        from app.workers import boas_vindas_convertidos
        with patch.object(boas_vindas_convertidos, "_fetch_convertidos", new_callable=AsyncMock) as m:
            m.return_value = []
            r = await boas_vindas_convertidos.disparar_boas_vindas()
            assert r == {"convertidos": 0, "enviados": 0, "falhas": 0}

    @pytest.mark.asyncio
    async def test_envia_e_remove(self):
        from app.workers import boas_vindas_convertidos
        convertidos = [{"id": 99, "nome": "Pedro", "telefone": "5581333"}]
        mock_uaz = MagicMock()
        mock_uaz.send_text = AsyncMock()
        with (
            patch.object(boas_vindas_convertidos, "_fetch_convertidos", new_callable=AsyncMock) as mc,
            patch.object(boas_vindas_convertidos, "_remover_convertido", new_callable=AsyncMock) as mrm,
            patch.object(boas_vindas_convertidos, "get_uaz_client", return_value=mock_uaz),
            patch.object(boas_vindas_convertidos, "_gerar_mensagem", new_callable=AsyncMock) as mmsg,
            patch.object(boas_vindas_convertidos.asyncio, "sleep", new_callable=AsyncMock),
        ):
            mc.return_value = convertidos
            mmsg.return_value = "Bem-vindo!"
            r = await boas_vindas_convertidos.disparar_boas_vindas()
        assert r["convertidos"] == 1
        assert r["enviados"] == 1
        mrm.assert_awaited_once_with(99)


# === cultos_gerador ===

class TestCultosGerador:
    @pytest.mark.asyncio
    async def test_chama_function(self):
        from app.workers import cultos_gerador
        mock_session = AsyncMock()
        count_result = MagicMock()
        count_result.scalar.return_value = 42
        mock_session.execute = AsyncMock(side_effect=[None, count_result])
        mock_session.commit = AsyncMock()

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock()
        mock_factory = MagicMock(return_value=mock_ctx)

        with patch.object(cultos_gerador, "async_session_factory", mock_factory):
            total = await cultos_gerador.gerar_cultos_proximos_meses()
        assert total == 42
