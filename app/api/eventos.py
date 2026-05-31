"""API de Eventos — CRUD do painel (substituindo Google Sheets)."""
from __future__ import annotations

import time
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import current_user
from app.core.config import settings
from app.db import get_db
from app.models.eventos import EventoPaes
from app.models.usuarios_painel import UsuarioPainel
from app.schemas.eventos import (
    CapaUploadResponse,
    EventoCreate,
    EventoOut,
    EventoUpdate,
)
from app.services import drive_client

router = APIRouter(prefix="/api/eventos", tags=["eventos"])

_SP_TZ = ZoneInfo("America/Sao_Paulo")


# ── GET ──────────────────────────────────────────────────

@router.get("", response_model=list[EventoOut])
async def list_eventos(
    periodo: str = Query("futuros", pattern=r"^(futuros|passados|todos)$"),
    origem: str = Query("todos", pattern=r"^(painel|sheets|todos)$"),
    db: AsyncSession = Depends(get_db),
    _user: UsuarioPainel = Depends(current_user),
):
    stmt = select(EventoPaes)

    today = datetime.now(_SP_TZ).date()
    if periodo == "futuros":
        stmt = stmt.where(
            (EventoPaes.data_inicio >= today) | (EventoPaes.data_final >= today)
        )
    elif periodo == "passados":
        stmt = stmt.where(
            (EventoPaes.data_inicio < today)
            & ((EventoPaes.data_final < today) | (EventoPaes.data_final.is_(None)))
        )

    if origem != "todos":
        stmt = stmt.where(EventoPaes.origem == origem)

    stmt = stmt.order_by(EventoPaes.data_inicio.asc().nullslast())
    result = await db.execute(stmt)
    return result.scalars().all()


# ── POST ─────────────────────────────────────────────────

@router.post("", response_model=EventoOut, status_code=201)
async def create_evento(
    body: EventoCreate,
    db: AsyncSession = Depends(get_db),
    user: UsuarioPainel = Depends(current_user),
):
    evento = EventoPaes(
        nome=body.nome,
        descricao=body.descricao,
        local=body.local,
        data_inicio=body.data_inicio,
        data_final=body.data_final or body.data_inicio,
        hora=body.hora,
        valor=body.valor,
        link=body.link,
        media=body.media,
        origem="painel",
        sheets_row_id=f"painel:{uuid.uuid4()}",
    )
    db.add(evento)
    await db.commit()
    await db.refresh(evento)
    return evento


# ── PATCH ────────────────────────────────────────────────

@router.patch("/{evento_id}", response_model=EventoOut)
async def update_evento(
    evento_id: int,
    body: EventoUpdate,
    db: AsyncSession = Depends(get_db),
    _user: UsuarioPainel = Depends(current_user),
):
    evento = await db.get(EventoPaes, evento_id)
    if not evento:
        raise HTTPException(404, "Evento não encontrado")

    # Conflito: evento vindo do Sheets
    if evento.origem == "sheets" and not body.confirmar_descolar:
        raise HTTPException(409, detail={
            "error": "evento_de_planilha",
            "message": "Este evento veio da planilha. Editar aqui vai desconectá-lo da planilha. Confirme?",
            "evento": EventoOut.model_validate(evento).model_dump(mode="json"),
        })

    # Descolar do Sheets
    if body.confirmar_descolar and evento.origem == "sheets":
        evento.sheets_row_id = f"painel:{uuid.uuid4()}"
        evento.origem = "painel"

    # UPDATE com COALESCE: só sobrescreve se valor não-vazio foi passado
    update_data = body.model_dump(exclude={"confirmar_descolar"}, exclude_unset=True)
    for field, value in update_data.items():
        if value is not None and value != "":
            setattr(evento, field, value)

    await db.commit()
    await db.refresh(evento)
    return evento


# ── DELETE ───────────────────────────────────────────────

@router.delete("/{evento_id}", status_code=204)
async def delete_evento(
    evento_id: int,
    confirmar_descolar: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    _user: UsuarioPainel = Depends(current_user),
):
    evento = await db.get(EventoPaes, evento_id)
    if not evento:
        raise HTTPException(404, "Evento não encontrado")

    if evento.origem == "sheets" and not confirmar_descolar:
        raise HTTPException(409, detail={
            "error": "evento_de_planilha",
            "message": "Este evento veio da planilha. Excluir aqui vai desconectá-lo. Confirme?",
            "evento": EventoOut.model_validate(evento).model_dump(mode="json"),
        })

    await db.delete(evento)
    await db.commit()


# ── UPLOAD CAPA ──────────────────────────────────────────

@router.post("/upload-capa", response_model=CapaUploadResponse)
async def upload_capa(
    file: UploadFile = File(...),
    _user: UsuarioPainel = Depends(current_user),
):
    file_bytes = await file.read()
    max_bytes = 5 * 1024 * 1024
    if len(file_bytes) > max_bytes:
        raise HTTPException(400, "Imagem maior que 5MB")

    mimetype = file.content_type or "image/jpeg"
    file_id = drive_client.upload_bytes(
        file_bytes,
        filename=f"evento_{int(time.time())}_{file.filename}",
        mimetype=mimetype,
        folder_id=settings.drive_folder_media,
    )
    url = drive_client.get_public_url(file_id)

    return CapaUploadResponse(media=url, size=len(file_bytes))
