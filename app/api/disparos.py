"""API de Disparos em Massa — CRUD + upload + contatos-count."""
from __future__ import annotations

import asyncio
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy import select, update, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import current_user
from app.core.config import settings
from app.db import get_db
from app.models.disparos import Disparo, DisparoLog
from app.models.usuarios_painel import UsuarioPainel
from app.schemas.disparos import (
    ContatosCountResponse,
    DisparoCreate,
    DisparoLogOut,
    DisparoOut,
    UploadResponse,
)
from app.services import drive_client
from app.services.disparo_service import check_lock, count_contatos

router = APIRouter(prefix="/api/disparos", tags=["disparos"])


@router.get("", response_model=list[DisparoOut])
async def list_disparos(
    db: AsyncSession = Depends(get_db),
    _user: UsuarioPainel = Depends(current_user),
):
    """Lista os últimos 50 disparos."""
    result = await db.execute(
        select(Disparo).order_by(desc(Disparo.created_at)).limit(50)
    )
    return result.scalars().all()


@router.get("/contatos-count", response_model=ContatosCountResponse)
async def get_contatos_count(
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: UsuarioPainel = Depends(current_user),
):
    """Contagem de contatos elegíveis."""
    count = await count_contatos(db, status_filter=status)
    return ContatosCountResponse(count=count)


@router.post("", response_model=DisparoOut, status_code=201)
async def create_disparo(
    body: DisparoCreate,
    db: AsyncSession = Depends(get_db),
    user: UsuarioPainel = Depends(current_user),
):
    """Cria novo disparo (imediato ou agendado)."""
    # Validar agendamento
    if not body.enviar_agora and not body.agendado_para:
        raise HTTPException(400, "Informe 'agendado_para' ou use 'enviar_agora=true'")

    # Lock global
    if await check_lock(db):
        raise HTTPException(409, "Já existe um disparo em andamento.")

    status = "enviando" if body.enviar_agora else "agendado"

    disparo = Disparo(
        arquivo_url=body.arquivo_url,
        arquivo_tipo=body.arquivo_tipo,
        arquivo_nome=body.arquivo_nome,
        legenda=body.legenda,
        status=status,
        agendado_para=None if body.enviar_agora else body.agendado_para,
        created_by=user.username,
        filtro_status=body.filtro_status,
        filtro_telefones=body.filtro_telefones,
    )
    db.add(disparo)
    await db.commit()
    await db.refresh(disparo)

    # Se imediato, dispara em background
    if body.enviar_agora:
        from app.workers.disparo_runner import run_disparo
        asyncio.create_task(run_disparo(disparo.id))

    return disparo


@router.patch("/{disparo_id}/cancelar", response_model=DisparoOut)
async def cancelar_disparo(
    disparo_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: UsuarioPainel = Depends(current_user),
):
    """Cancela um disparo agendado ou em execução."""
    result = await db.execute(
        update(Disparo)
        .where(Disparo.id == disparo_id, Disparo.status.in_(["agendado", "enviando"]))
        .values(status="cancelado")
        .returning(Disparo)
    )
    disparo = result.scalar_one_or_none()
    if not disparo:
        raise HTTPException(404, "Disparo não encontrado ou já finalizado")
    await db.commit()
    await db.refresh(disparo)
    return disparo


@router.get("/{disparo_id}/log", response_model=list[DisparoLogOut])
async def get_disparo_log(
    disparo_id: uuid.UUID,
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _user: UsuarioPainel = Depends(current_user),
):
    """Log de envio paginado."""
    result = await db.execute(
        select(DisparoLog)
        .where(DisparoLog.disparo_id == disparo_id)
        .order_by(DisparoLog.enviado_em.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


@router.post("/upload", response_model=UploadResponse)
async def upload_arquivo(
    file: UploadFile = File(...),
    _user: UsuarioPainel = Depends(current_user),
):
    """Upload de arquivo para Google Drive → retorna URL pública."""
    file_bytes = await file.read()
    max_bytes = settings.disparos_max_file_mb * 1024 * 1024
    if len(file_bytes) > max_bytes:
        raise HTTPException(400, f"Arquivo maior que {settings.disparos_max_file_mb}MB")

    mimetype = file.content_type or "application/octet-stream"
    folder = settings.disparos_drive_folder or settings.drive_folder_media

    file_id = drive_client.upload_bytes(
        file_bytes,
        filename=f"disparo_{int(time.time())}_{file.filename}",
        mimetype=mimetype,
        folder_id=folder,
    )
    url = drive_client.get_public_url(file_id)
    tipo = drive_client.detect_uaz_type(mimetype)

    return UploadResponse(
        arquivo_url=url,
        arquivo_nome=file.filename or "arquivo",
        arquivo_tipo=tipo,
        mimetype=mimetype,
        size=len(file_bytes),
    )
