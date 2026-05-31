"""Testes de autenticação — login, JWT, proteção de endpoints."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.auth_service import create_token, decode_token, hash_password, verify_password


class TestPasswordHashing:
    def test_hash_and_verify(self):
        pw = "minha_senha_123"
        hashed = hash_password(pw)
        assert hashed != pw
        assert verify_password(pw, hashed) is True

    def test_wrong_password(self):
        hashed = hash_password("correta")
        assert verify_password("errada", hashed) is False


class TestJWT:
    def test_create_and_decode(self, monkeypatch):
        monkeypatch.setattr("app.services.auth_service.settings", MagicMock(
            painel_jwt_secret="test-secret",
            painel_jwt_expire_hours=12,
        ))
        token, expires = create_token("admin")
        assert expires == 43200
        assert isinstance(token, str)

        monkeypatch.setattr("app.services.auth_service.settings", MagicMock(
            painel_jwt_secret="test-secret",
        ))
        username = decode_token(token)
        assert username == "admin"

    def test_invalid_token(self, monkeypatch):
        monkeypatch.setattr("app.services.auth_service.settings", MagicMock(
            painel_jwt_secret="test-secret",
        ))
        import jwt as pyjwt
        with pytest.raises(pyjwt.PyJWTError):
            decode_token("token.invalido.aqui")

    def test_wrong_secret(self, monkeypatch):
        monkeypatch.setattr("app.services.auth_service.settings", MagicMock(
            painel_jwt_secret="secret-1",
            painel_jwt_expire_hours=12,
        ))
        token, _ = create_token("admin")

        monkeypatch.setattr("app.services.auth_service.settings", MagicMock(
            painel_jwt_secret="secret-2",
        ))
        import jwt as pyjwt
        with pytest.raises(pyjwt.PyJWTError):
            decode_token(token)


class TestCurrentUserDependency:
    @pytest.mark.asyncio
    async def test_missing_header_raises_401(self):
        from app.api.auth import current_user
        with pytest.raises(Exception) as exc:
            await current_user(authorization=None, db=AsyncMock())
        assert "401" in str(exc.value.status_code)

    @pytest.mark.asyncio
    async def test_invalid_token_raises_401(self):
        from app.api.auth import current_user
        with pytest.raises(Exception) as exc:
            await current_user(authorization="Bearer bad.token.here", db=AsyncMock())
        assert "401" in str(exc.value.status_code)
