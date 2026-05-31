"""Auth endpoints + dependency current_user."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.usuarios_painel import UsuarioPainel
from app.services.auth_service import create_token, decode_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    expires_in: int
    username: str


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(
        select(UsuarioPainel).where(UsuarioPainel.username == body.username)
    )
    if not user or not user.ativo:
        raise HTTPException(401, "Credenciais inválidas")
    if not verify_password(body.password, user.senha_hash):
        raise HTTPException(401, "Credenciais inválidas")

    token, expires_in = create_token(user.username)
    return LoginResponse(
        access_token=token,
        expires_in=expires_in,
        username=user.username,
    )


async def current_user(
    authorization: str = Header(None),
    db: AsyncSession = Depends(get_db),
) -> UsuarioPainel:
    """Dependency FastAPI — extrai e valida JWT do header Authorization."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Token ausente")
    token = authorization.split(" ", 1)[1]
    try:
        username = decode_token(token)
    except Exception:
        raise HTTPException(401, "Token inválido")
    user = await db.scalar(
        select(UsuarioPainel).where(UsuarioPainel.username == username)
    )
    if not user or not user.ativo:
        raise HTTPException(401, "Usuário inativo")
    return user
