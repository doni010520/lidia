from __future__ import annotations

from sqlalchemy import Boolean, Integer, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class EquipeResponsavel(Base):
    __tablename__ = "equipes_responsaveis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    equipe: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text)
    telefones_responsaveis = mapped_column(ARRAY(Text))
    emails = mapped_column(ARRAY(Text))
    sheets_log_url: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
