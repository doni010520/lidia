"""Disparo só de texto e áudio como mensagem de voz (ptt)."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from app.schemas.disparos import DisparoCreate


class TestSchema:
    def test_texto_so_com_mensagem(self):
        d = DisparoCreate(tipo="texto", legenda=" Bom dia! ", enviar_agora=True)
        assert d.legenda == "Bom dia!"

    def test_texto_sem_mensagem_recusa(self):
        with pytest.raises(ValidationError):
            DisparoCreate(tipo="texto", legenda="  ", enviar_agora=True)

    def test_audio_sem_legenda_ok(self):
        d = DisparoCreate(
            tipo="midia", arquivo_url="https://drive/a.ogg", arquivo_tipo="ptt",
            enviar_agora=True,
        )
        assert d.legenda is None

    def test_imagem_sem_legenda_recusa(self):
        with pytest.raises(ValidationError):
            DisparoCreate(
                tipo="midia", arquivo_url="https://drive/a.jpg", arquivo_tipo="image",
                enviar_agora=True,
            )


def _disparo(**campos):
    from app.models.disparos import Disparo

    d = MagicMock(spec=Disparo)
    d.id = uuid.uuid4()
    d.status = "enviando"
    d.total = d.enviados = d.falhas = 0
    d.arquivo_url = d.arquivo_tipo = d.legenda = None
    d.contato_nome = d.contato_telefone = d.contato_organizacao = None
    for k, v in campos.items():
        setattr(d, k, v)
    return d


async def _rodar(disparo, uaz):
    db = AsyncMock()
    db.get.return_value = disparo
    db.add = MagicMock()
    db.scalar.return_value = None  # nenhum log existente
    contatos = [{"telefone": "5581999", "nome": "João"}]
    with (
        patch("app.workers.disparo_runner.async_session_factory") as sf,
        patch("app.workers.disparo_runner.get_uaz_client", return_value=uaz),
        patch("app.workers.disparo_runner.fetch_contatos", new_callable=AsyncMock, return_value=contatos),
        patch("app.workers.disparo_runner.dentro_da_janela", return_value=True),
        patch("app.workers.disparo_runner.settings", MagicMock(disparos_delay_seconds=0)),
        patch("app.workers.disparo_runner.asyncio") as aio,
    ):
        aio.sleep = AsyncMock()
        sf.return_value.__aenter__ = AsyncMock(return_value=db)
        sf.return_value.__aexit__ = AsyncMock(return_value=False)
        from app.workers.disparo_runner import _loop_envio
        await _loop_envio(disparo.id)


def _uaz():
    uaz = MagicMock()
    uaz.send_text = AsyncMock()
    uaz.send_media = AsyncMock()
    uaz.send_contact = AsyncMock()
    return uaz


class TestRunner:
    @pytest.mark.asyncio
    async def test_texto_envia_so_texto(self):
        uaz = _uaz()
        d = _disparo(tipo="texto", legenda="Bom dia, PAES!")
        await _rodar(d, uaz)
        uaz.send_text.assert_awaited_once()
        assert uaz.send_text.await_args.args == ("5581999", "Bom dia, PAES!")
        uaz.send_media.assert_not_awaited()
        assert d.enviados == 1

    @pytest.mark.asyncio
    async def test_audio_vai_como_voz_sem_legenda(self):
        uaz = _uaz()
        d = _disparo(tipo="midia", arquivo_url="https://drive/a.ogg", arquivo_tipo="ptt")
        await _rodar(d, uaz)
        uaz.send_text.assert_not_awaited()
        kw = uaz.send_media.await_args.kwargs
        assert kw["type"] == "ptt"
        assert "text" not in kw
        assert d.enviados == 1

    @pytest.mark.asyncio
    async def test_audio_com_legenda_manda_texto_antes(self):
        uaz = _uaz()
        ordem = []
        uaz.send_text.side_effect = lambda *a, **k: ordem.append("texto")
        uaz.send_media.side_effect = lambda *a, **k: ordem.append("audio")
        d = _disparo(
            tipo="midia", arquivo_url="https://drive/a.ogg", arquivo_tipo="ptt",
            legenda="Ouça o recado do pastor",
        )
        await _rodar(d, uaz)
        assert ordem == ["texto", "audio"]
