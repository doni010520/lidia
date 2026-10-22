"""Telefone das chamadas Diacon vem SEMPRE do remetente (guia Diacon 22/10/26).

Antes o número que o modelo punha em 'telefone' vencia quando tinha >=10
dígitos: "me manda o relatório do 81 99788-4531" entregava o relatório do
dono desse número (e o panorama de admin, a quem digitasse o número de um).
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

from app.tools.tool_modules import buscar_evento as be
from app.tools.tool_modules._phone import resolve_phone


def test_numero_digitado_nao_vence_o_remetente():
    assert resolve_phone("81997884531", "557193061031") == "557193061031"
    assert resolve_phone("(81) 99788-4531", "557193061031") == "557193061031"


def test_lixo_do_modelo_cai_no_remetente():
    assert resolve_phone("(não informado)", "557193061031") == "557193061031"


def test_sem_remetente_usa_o_arg_so_se_for_telefone():
    assert resolve_phone("81997884531", "") == "81997884531"
    assert resolve_phone("não sei", "") == ""


@pytest.mark.asyncio
async def test_agenda_manda_o_telefone_do_remetente(monkeypatch):
    fake = AsyncMock(return_value={"events": []})
    monkeypatch.setattr(be.diacon_client, "is_enabled", lambda: True)
    monkeypatch.setattr(be.diacon_client, "events_upcoming", fake)

    await be.execute({"nome_evento": "Retiro"}, "558197884531", AsyncMock())

    assert all(c.kwargs["phone"] == "558197884531" for c in fake.await_args_list)
    assert all(c.kwargs["limit"] <= 300 for c in fake.await_args_list)
