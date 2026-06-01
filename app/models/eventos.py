from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class EventoPaes(Base):
    __tablename__ = "eventos_paes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(Text, nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text)
    local: Mapped[str | None] = mapped_column(Text)
    data_inicio: Mapped[date | None] = mapped_column(Date)
    data_final: Mapped[date | None] = mapped_column(Date)
    hora: Mapped[str | None] = mapped_column(Text)  # formato livre: "18hrs", "manhã", etc
    valor: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(Text)
    media: Mapped[str | None] = mapped_column(Text)
    sheets_row_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # ── Campo novo (migration 005) ──
    origem: Mapped[str] = mapped_column(
        String(20), default="painel", server_default="painel"
    )

    __table_args__ = (
        CheckConstraint("origem IN ('sheets', 'painel')", name="ck_eventos_origem"),
        Index("idx_eventos_data", "data_inicio", "data_final"),
    )
