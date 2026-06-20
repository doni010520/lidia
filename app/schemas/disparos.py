"""Schemas Pydantic para o módulo de Disparos."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class DisparoCreate(BaseModel):
    tipo: str = Field(default="midia", pattern=r"^(midia|contato)$")
    # Mídia (tipo='midia')
    arquivo_url: str | None = None
    arquivo_tipo: str | None = Field(default=None, pattern=r"^(image|document|video)$")
    arquivo_nome: str | None = None
    legenda: str = Field(min_length=1, max_length=4096)
    # Contato (tipo='contato')
    contato_nome: str | None = Field(default=None, max_length=120)
    contato_telefone: str | None = Field(default=None, max_length=200)
    contato_organizacao: str | None = Field(default=None, max_length=120)
    # Comuns
    agendado_para: datetime | None = None
    enviar_agora: bool = False
    filtro_status: str | None = None
    filtro_telefones: list[str] | None = None

    @model_validator(mode="after")
    def _validar_por_tipo(self) -> "DisparoCreate":
        if self.tipo == "midia":
            if not self.arquivo_url or not self.arquivo_tipo:
                raise ValueError("Disparo de mídia exige 'arquivo_url' e 'arquivo_tipo'.")
        elif self.tipo == "contato":
            if not self.contato_nome or not self.contato_telefone:
                raise ValueError("Disparo de contato exige 'contato_nome' e 'contato_telefone'.")
        return self


class DisparoOut(BaseModel):
    id: uuid.UUID
    tipo: str = "midia"
    arquivo_url: str | None = None
    arquivo_tipo: str | None = None
    arquivo_nome: str | None
    legenda: str | None
    contato_nome: str | None = None
    contato_telefone: str | None = None
    contato_organizacao: str | None = None
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
