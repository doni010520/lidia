from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Disparo(Base):
    __tablename__ = "disparos"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    arquivo_url: Mapped[str] = mapped_column(Text, nullable=False)
    arquivo_tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    arquivo_nome: Mapped[str | None] = mapped_column(String(255))
    legenda: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="agendado", server_default="agendado")
    agendado_para: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    enviados: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    falhas: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    filtro_status: Mapped[str | None] = mapped_column(Text)
    filtro_telefones = mapped_column(ARRAY(Text), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(100))

    __table_args__ = (
        CheckConstraint(
            "arquivo_tipo IN ('image', 'document', 'video')",
            name="ck_disparo_arquivo_tipo",
        ),
        CheckConstraint(
            "status IN ('agendado', 'enviando', 'concluido', 'falhou', 'cancelado')",
            name="ck_disparo_status",
        ),
        Index("idx_disparos_status", "status"),
        Index("idx_disparos_agendado", "agendado_para", postgresql_where="status = 'agendado'"),
    )


class DisparoLog(Base):
    __tablename__ = "disparo_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    disparo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("disparos.id", ondelete="CASCADE"), nullable=False
    )
    telefone: Mapped[str] = mapped_column(String(20), nullable=False)
    nome: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default="enviado", server_default="enviado")
    enviado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    erro: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(
            "status IN ('enviado', 'falhou', 'pulado')",
            name="ck_disparo_log_status",
        ),
        Index("idx_disparo_log_disparo", "disparo_id"),
        UniqueConstraint("disparo_id", "telefone", name="uq_disparo_log_pair"),
    )
