"""Schemas Pydantic para o módulo de Disparos."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class DisparoCreate(BaseModel):
    arquivo_url: str
    arquivo_tipo: str = Field(pattern=r"^(image|document|video)$")
    arquivo_nome: str | None = None
    legenda: str = Field(min_length=1, max_length=4096)
    agendado_para: datetime | None = None
    enviar_agora: bool = False
    filtro_status: str | None = None
    filtro_telefones: list[str] | None = None


class DisparoOut(BaseModel):
    id: uuid.UUID
    arquivo_url: str
    arquivo_tipo: str
    arquivo_nome: str | None
    legenda: str | None
    status: str
    agendado_para: datetime | None
    total: int
    enviados: int
    falhas: int
    filtro_status: str | None
    filtro_telefones: list[str] | None
    created_at: datetime
    created_by: str | None

    model_config = {"from_attributes": True}


class DisparoLogOut(BaseModel):
    id: int
    disparo_id: uuid.UUID
    telefone: str
    nome: str | None
    status: str
    enviado_em: datetime
    erro: str | None

    model_config = {"from_attributes": True}


class UploadResponse(BaseModel):
    arquivo_url: str
    arquivo_nome: str
    arquivo_tipo: str
    mimetype: str
    size: int


class ContatosCountResponse(BaseModel):
    count: int
