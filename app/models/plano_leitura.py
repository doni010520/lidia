from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PlanoLeitura(Base):
    __tablename__ = "plano_de_leitura"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    data: Mapped[date] = mapped_column(Date, unique=True)
    leitura: Mapped[str | None] = mapped_column(Text)
    capitulos: Mapped[str | None] = mapped_column(Text)
    semana: Mapped[int | None] = mapped_column(Integer)
    livro: Mapped[str | None] = mapped_column(Text)
    sheets_row_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
