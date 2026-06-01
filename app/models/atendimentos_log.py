from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class AtendimentoLog(Base):
    __tablename__ = "paes_atendimentos_log"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    contact_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("contacts.id", ondelete="SET NULL")
    )
    telefone: Mapped[str] = mapped_column(Text, nullable=False)
    nome: Mapped[str | None] = mapped_column(Text)
    status_momento: Mapped[str | None] = mapped_column(Text)
    ministerio_momento: Mapped[str | None] = mapped_column(Text)
    data_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    tipo_interacao: Mapped[str | None] = mapped_column(Text, server_default="atendimento")
    __table_args__ = (
        Index("idx_atendimentos_telefone", "telefone"),
        Index("idx_atendimentos_data", "data_hora"),
        Index("idx_atendimentos_contact", "contact_id"),
    )
