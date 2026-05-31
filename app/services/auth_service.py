"""Auth service — bcrypt password hashing + JWT tokens."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    return bcrypt.checkpw(pw.encode(), hashed.encode())


def create_token(username: str) -> tuple[str, int]:
    exp_hours = settings.painel_jwt_expire_hours
    payload = {
        "sub": username,
        "exp": datetime.now(timezone.utc) + timedelta(hours=exp_hours),
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, settings.painel_jwt_secret, algorithm="HS256")
    return token, exp_hours * 3600


def decode_token(token: str) -> str:
    """Retorna username ou lança jwt.PyJWTError."""
    payload = jwt.decode(token, settings.painel_jwt_secret, algorithms=["HS256"])
    return payload["sub"]
