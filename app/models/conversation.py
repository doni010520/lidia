from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telefone: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    nome: Mapped[str | None] = mapped_column(Text)
    full_name: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)
    aniversario: Mapped[date | None] = mapped_column(Date)
    ultimo_contato: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ai_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    cadastro_completo: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    # ── Campos trazidos do schema Supabase (migration 008) ──
    pediu_aniversario: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    follow_up: Mapped[str | None] = mapped_column(Text)
    etiqueta: Mapped[str | None] = mapped_column(Text)
    ministerio_de_interesse: Mapped[str | None] = mapped_column(Text)
    ministerio_de_servico: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_contacts_telefone", "telefone"),
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phone: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_call_id: Mapped[str | None] = mapped_column(Text)
    tool_name: Mapped[str | None] = mapped_column(Text)
    tool_calls_json: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_messages_phone_created", "phone", "created_at"),
    )
