"""Schemas Pydantic para o módulo de Eventos."""
from __future__ import annotations

from datetime import date, datetime, time

from pydantic import BaseModel, Field


class EventoCreate(BaseModel):
    nome: str = Field(..., min_length=1, max_length=255)
    descricao: str | None = None
    local: str | None = None
    data_inicio: date
    data_final: date | None = None
    hora: time | None = None
    valor: str | None = None
    link: str | None = None
    media: str | None = None


class EventoUpdate(BaseModel):
    nome: str | None = None
    descricao: str | None = None
    local: str | None = None
    data_inicio: date | None = None
    data_final: date | None = None
    hora: time | None = None
    valor: str | None = None
    link: str | None = None
    media: str | None = None
    confirmar_descolar: bool = False


class EventoOut(BaseModel):
    id: int
    nome: str
    descricao: str | None
    local: str | None
    data_inicio: date | None
    data_final: date | None
    hora: time | None
    valor: str | None
    link: str | None
    media: str | None
    origem: str
    sheets_row_id: str | None
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class CapaUploadResponse(BaseModel):
    media: str
    size: int
