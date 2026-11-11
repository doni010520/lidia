"""Comunicado com botão para a base da Diacon (devocional 2027, nov/26).

Guia Diacon §5b: lista lida na hora (paginando por `after`), quem saiu não
recebe, e a saída só é confirmada depois do 200.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import campanha_cursilho as cc
from app.services import disparo_service as ds
from app.tools.tool_modules import parar_comunicados as pc
from app.workers import disparo_runner as dr


@pytest.mark.asyncio
async def test_lista_pagina_por_after(monkeypatch):
    pages = [
        {"members": [{"phone": "+5581999990001", "first_name": "Ana"}], "has_next": True, "next_after": "u1"},
        {"members": [{"phone": "+5581999990002", "first_name": "Bia"}], "has_next": False},
    ]
    fake = AsyncMock(side_effect=pages)
    from app.services import diacon_client
    monkeypatch.setattr(diacon_client, "members_list", fake)

    out = await ds._contatos_diacon()

    assert [c["telefone"] for c in out] == ["5581999990001", "5581999990002"]
    assert fake.await_args_list[1].kwargs["after"] == "u1"


def test_rodada_vem_do_filtro():
    assert ds.rodada_da_campanha(MagicMock(filtro_status="campanha:devocional")) == "devocional"
    assert ds.rodada_da_campanha(MagicMock(filtro_status="membro")) is None


@pytest.mark.asyncio
async def test_quem_saiu_e_pulado(monkeypatch):
    from app.services import diacon_client
    monkeypatch.setattr(diacon_client, "member_lookup", AsyncMock(
        return_value={"found": True, "member": {"first_name": "Ana", "allow_contact": False}}))
    uaz = MagicMock(check_number=AsyncMock())
    numero, _, motivo = await dr._destino_campanha(uaz, "5581999990001")
    assert numero is None and "não aceita" in motivo
    uaz.check_number.assert_not_awaited()


@pytest.mark.asyncio
async def test_sem_whatsapp_e_pulado_e_numero_vem_do_jid(monkeypatch):
    from app.services import diacon_client
    monkeypatch.setattr(diacon_client, "member_lookup", AsyncMock(
        return_value={"found": True, "member": {"first_name": "Ana", "allow_contact": True}}))
    uaz = MagicMock(check_number=AsyncMock(return_value=[{"isInWhatsapp": False}]))
    assert (await dr._destino_campanha(uaz, "5581999990001"))[2] == "número sem WhatsApp"
    uaz.check_number = AsyncMock(return_value=[{"isInWhatsapp": True, "jid": "558199990001@s.whatsapp.net"}])
    assert await dr._destino_campanha(uaz, "5581999990001") == ("558199990001", "Ana", None)


@pytest.mark.asyncio
async def test_convite_do_devocional_tem_botao_de_saida(monkeypatch):
    monkeypatch.setattr(cc, "save_message", AsyncMock())
    uaz = MagicMock(_post=AsyncMock(return_value={}))
    await cc.enviar_convite(uaz, AsyncMock(), "5581", "Maria Silva", "devocional")
    body = uaz._post.await_args.args[1]
    assert body["choices"] == ["Quero ver 🎁|devocional_ver", f"{cc.SAIR_LABEL}|{cc.SAIR_ID}"]
    assert body["text"].startswith("Oi, Maria!")
    assert all(len(c.split("|")[0]) <= 20 for c in body["choices"])


@pytest.mark.asyncio
async def test_botao_sair_grava_na_diacon_e_confirma(monkeypatch):
    from app.services import diacon_client
    upd = AsyncMock(return_value={"ok": True, "contact_choice": "saved", "member": {"first_name": "Maria"}})
    monkeypatch.setattr(diacon_client, "member_update", upd)
    monkeypatch.setattr(cc, "save_message", AsyncMock())
    uaz = MagicMock(send_text=AsyncMock())
    await cc.responder_clique(uaz, AsyncMock(), "5581", cc.SAIR_ID)
    upd.assert_awaited_once_with(phone="5581", allow_contact=False)
    assert "não vai mais receber" in uaz.send_text.await_args.args[1]


@pytest.mark.asyncio
async def test_botao_sair_falhou_nao_diz_que_saiu(monkeypatch):
    from app.services import diacon_client
    monkeypatch.setattr(diacon_client, "member_update",
                        AsyncMock(side_effect=diacon_client.DiaconError("x", status=500)))
    monkeypatch.setattr(cc, "save_message", AsyncMock())
    uaz = MagicMock(send_text=AsyncMock())
    await cc.responder_clique(uaz, AsyncMock(), "5581", cc.SAIR_ID)
    assert "Não consegui" in uaz.send_text.await_args.args[1]


@pytest.mark.asyncio
async def test_parar_por_texto_usa_o_remetente(monkeypatch):
    upd = AsyncMock(return_value={"ok": True, "contact_choice": "saved"})
    monkeypatch.setattr(pc.diacon_client, "is_enabled", lambda: True)
    monkeypatch.setattr(pc.diacon_client, "member_update", upd)
    out = await pc.execute({"telefone": "81997884531"}, "558199990001", AsyncMock())
    upd.assert_awaited_once_with(phone="558199990001", allow_contact=False)
    assert out.startswith("Pronto")
