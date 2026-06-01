from __future__ import annotations
from datetime import datetime
from sqlalchemy import BigInteger, DateTime, Index, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class Lideranca(Base):
    __tablename__ = "liderancas"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    nome: Mapped[str | None] = mapped_column(Text)
    telefone: Mapped[str | None] = mapped_column(Text)
    ministerio: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (Index("idx_liderancas_telefone", "telefone"),)


class PastorAniversario(Base):
    __tablename__ = "pastores_aniversario"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    nome: Mapped[str | None] = mapped_column(Text)
    telefone: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (Index("idx_pastores_telefone", "telefone"),)
