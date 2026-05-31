from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class NovoConvertido(Base):
    __tablename__ = "novos_convertidos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telefone: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    nome: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
