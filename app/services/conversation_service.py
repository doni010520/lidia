"""Pipeline principal de conversação.

Sequência completa: contact → mídia → RAG → agente → LLM → envio em partes.
"""
from __future__ import annotations

import asyncio
import locale
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from loguru import logger
from sqlalchemy import select, insert, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import lidia, lidia_cadastro
from app.core.config import settings
from app.models.conversation import Contact, Message
from app.schemas.webhook import IncomingMessage
from app.services.deps import get_uaz_client
from app.services.openai_service import OpenAIService
from app.services.rag_service import RAGService

_SP_TZ = ZoneInfo("America/Sao_Paulo")

# Meses em pt-BR para formatação
_MESES_PT = {
    1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril",
    5: "maio", 6: "junho", 7: "julho", 8: "agosto",
    9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro",
}
_DIAS_PT = {
    0: "segunda-feira", 1: "terça-feira", 2: "quarta-feira",
    3: "quinta-feira", 4: "sexta-feira", 5: "sábado", 6: "domingo",
}


def now_sao_paulo_formatted() -> str:
    """Data/hora formatada em pt-BR no fuso de São Paulo."""
    now = datetime.now(_SP_TZ)
    dia_semana = _DIAS_PT[now.weekday()]
    mes = _MESES_PT[now.month]
    return f"{dia_semana}, {now.day:02d} de {mes} de {now.year} {now.hour:02d}:{now.minute:02d}"


# ── Singletons (inicializados no primeiro uso) ──

_rag: RAGService | None = None
_openai: OpenAIService | None = None


def _get_rag() -> RAGService:
    global _rag
    if _rag is None:
        _rag = RAGService()
    return _rag


def _get_openai() -> OpenAIService:
    global _openai
    if _openai is None:
        _openai = OpenAIService()
    return _openai


# ── Helpers de banco ──

async def get_or_create_contact(
    db: AsyncSession,
    phone: str,
    name: str | None = None,
) -> Contact:
    """Busca contato por telefone ou cria novo."""
    result = await db.execute(
        select(Contact).where(Contact.telefone == phone)
    )
    contact = result.scalar_one_or_none()

    if contact is None:
        contact = Contact(
            telefone=phone,
            nome=name,
            full_name=name,
        )
        db.add(contact)
        # Commit imediato para novo contato: garante que o registro existe no banco
        # antes de qualquer operação subsequente no pipeline (ex: save_message com FK
        # implícito, ou se o processo crashar, o contato já está persistido).
        await db.commit()
        await db.refresh(contact)
        logger.bind(phone=phone).info(f"Novo contato criado: {name}")
    else:
        # Atualizar nome se veio preenchido no webhook e está vazio no DB
        updated = False
        if name and not contact.nome:
            contact.nome = name
            updated = True
        if name and not contact.full_name:
            contact.full_name = name
            updated = True
        if updated:
            await db.flush()

    return contact


async def load_history(
    db: AsyncSession,
    phone: str,
    limit: int = 40,
) -> list[dict]:
    """Carrega últimas N mensagens do telefone como lista de dicts OpenAI."""
    result = await db.execute(
        select(Message)
        .where(Message.phone == phone)
        .order_by(desc(Message.created_at))
        .limit(limit)
    )
    rows = list(reversed(result.scalars().all()))

    history: list[dict] = []
    for row in rows:
        entry: dict = {"role": row.role, "content": row.content}
        if row.tool_call_id:
            entry["tool_call_id"] = row.tool_call_id
        if row.tool_calls_json:
            entry["tool_calls"] = row.tool_calls_json
        if row.tool_name:
            entry["name"] = row.tool_name
        history.append(entry)

    return history


async def save_message(
    db: AsyncSession,
    phone: str,
    role: str,
    content: str,
    *,
    tool_call_id: str | None = None,
    tool_name: str | None = None,
    tool_calls_json: dict | list | None = None,
) -> None:
    """Persiste uma mensagem no histórico."""
    await db.execute(
        insert(Message).values(
            phone=phone,
            role=role,
            content=content or "",
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            tool_calls_json=tool_calls_json,
        )
    )


# ── Pipeline principal ──

async def process_message(msg: IncomingMessage, db: AsyncSession) -> None:
    """Pipeline completo de processamento de mensagem.

    Corresponde à seção 9 do plano de migração.
    """
    uaz = get_uaz_client()
    log = logger.bind(phone=msg.phone, message_id=msg.message_id)

    # ── 1. Buscar/criar contato ──
    contact = await get_or_create_contact(db, msg.phone, msg.name)
    if contact.is_blocked:
        log.debug("Contato bloqueado, ignorando")
        return
    if not contact.ai_enabled:
        log.debug("AI desabilitada (handoff), ignorando")
        return

    # ── 2. Processar mídia → texto ──
    from app.services import media_processor

    user_text = msg.text or ""
    if msg.media_type and msg.message_id:
        if msg.media_type == "audio":
            transcription = await media_processor.transcribe_audio(msg.message_id)
            if transcription:
                user_text = transcription + ("\n" + user_text if user_text else "")
                log.info(f"Áudio transcrito: {transcription[:80]}...")

        elif msg.media_type == "image":
            description = await media_processor.describe_image(msg.message_id, msg.mimetype)
            user_text = description + ("\n" + user_text if user_text else "")
            log.info("Imagem descrita via GPT Vision")

        elif msg.media_type == "document":
            doc_text = await media_processor.extract_document(msg.message_id, msg.mimetype)
            user_text = doc_text + ("\n" + user_text if user_text else "")
            log.info(f"Documento extraído ({msg.mimetype})")

        elif msg.media_type == "video":
            file_id = await media_processor.handle_video(msg.message_id)
            if file_id:
                user_text = f"[SISTEMA] Usuário enviou vídeo. drive_file_id: {file_id}\n{user_text}"
                log.info(f"Vídeo uploaded para Drive: {file_id}")
            else:
                user_text = "[SISTEMA] Usuário enviou vídeo, mas não foi possível processar.\n" + user_text

    if not user_text.strip():
        log.debug("Mensagem sem texto, ignorando")
        return

    # ── 3. Pré-busca RAG ──
    rag = _get_rag()
    oai = _get_openai()
    hint = await rag.retrieve_hint(user_text, db)

    # ── 4. Escolher agente ──
    if not contact.cadastro_completo:
        agent_module = lidia_cadastro
        agent_type = "cadastro"
    else:
        agent_module = lidia
        agent_type = "atendimento"

    # ── 5. Montar system prompt ──
    system_prompt = agent_module.build_system_prompt(
        nome_usuario=contact.nome or contact.full_name or "",
        telefone=contact.telefone,
        data_atual=now_sao_paulo_formatted(),
        dica_rag=hint,
    )

    # ── 6. Carregar histórico ──
    history = await load_history(db, msg.phone, limit=settings.history_limit)

    # ── 7. Anexar mensagem atual + salvar ──
    history.append({"role": "user", "content": user_text})
    await save_message(db, msg.phone, "user", user_text)

    # ── 8. Analytics start ──
    from app.services import analytics_service
    analytics_ctx = analytics_service.start(
        phone=msg.phone, agent_type=agent_type, input_text=user_text,
    )

    # ── 9. Indicar "digitando..." ──
    try:
        await uaz.send_presence(msg.phone, "composing", delay=2000)
    except Exception:
        log.warning("Falha ao enviar presence")

    # ── 10. Chamar OpenAI com tool handler ──
    tools = agent_module.tools_allowed

    # Closure que injeta db no handler
    from app.tools.handlers import handle_tool_call

    async def _tool_handler(tool_name: str, args: dict, phone: str) -> str:
        return await handle_tool_call(tool_name, args, phone, db=db)

    reply_text, updated_history, tools_called = await oai.chat(
        messages=history,
        system_prompt=system_prompt,
        tools=tools if tools else None,
        phone=msg.phone,
        tool_handler=_tool_handler,
    )

    # ── 11. Persistir novas mensagens do tool loop ──
    new_entries = updated_history[len(history):]
    for entry in new_entries:
        await save_message(
            db,
            msg.phone,
            entry["role"],
            entry.get("content", ""),
            tool_call_id=entry.get("tool_call_id"),
            tool_calls_json=entry.get("tool_calls"),
        )

    # ── 12. Analytics capture ──
    await analytics_service.capture(analytics_ctx, reply_text, tools_called, db)

    # ── 13. Atualizar ultimo_contato ──
    contact.ultimo_contato = datetime.now(UTC)
    await db.commit()

    # ── 14. Enviar resposta em partes ──
    if reply_text:
        parts = [p.strip() for p in reply_text.split("\n\n") if p.strip()]
        log.info(f"Enviando resposta ({len(parts)} partes, agent={agent_type})")
        for part in parts:
            clean = part.replace("*", "")
            try:
                await uaz.send_text(msg.phone, clean)
            except Exception:
                log.exception(f"Erro ao enviar parte: {clean[:60]}...")
            await asyncio.sleep(1)
