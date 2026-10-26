"""confirmar_membro: a própria pessoa passa de visitante a membro (23/10/26, Myrian)."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.tools.tool_modules import confirmar_membro as cm


@pytest.fixture
def diacon(monkeypatch):
    monkeypatch.setattr(cm.diacon_client, "is_enabled", lambda: True)
    upd = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(cm.diacon_client, "member_update", upd)
    return upd


def _lookup(monkeypatch, resp):
    monkeypatch.setattr(cm.diacon_client, "member_lookup", AsyncMock(return_value=resp))


@pytest.mark.asyncio
async def test_visitante_vira_membro_pelo_telefone_do_remetente(monkeypatch, diacon):
    _lookup(monkeypatch, {"found": True, "member": {"first_name": "Myrian", "status": "visitor"}})
    out = await cm.execute({"telefone": "81997884531"}, "558197387992", AsyncMock())
    diacon.assert_awaited_once_with(phone="558197387992", status="active")
    assert "visitante para membro" in out


@pytest.mark.asyncio
async def test_ja_membro_nao_altera(monkeypatch, diacon):
    _lookup(monkeypatch, {"found": True, "member": {"first_name": "Ana", "status": "active"}})
    out = await cm.execute({}, "5581", AsyncMock())
    diacon.assert_not_awaited()
    assert "já está" in out


@pytest.mark.asyncio
async def test_inativo_fica_com_a_secretaria(monkeypatch, diacon):
    _lookup(monkeypatch, {"found": True, "member": {"first_name": "Rui", "status": "inactive"}})
    out = await cm.execute({}, "5581", AsyncMock())
    diacon.assert_not_awaited()
    assert "secretaria" in out


@pytest.mark.asyncio
async def test_sem_cadastro_manda_cadastrar(monkeypatch, diacon):
    _lookup(monkeypatch, {"found": False})
    out = await cm.execute({}, "5581", AsyncMock())
    diacon.assert_not_awaited()
    assert "cadastrar_contato" in out
