"""Tool: minha_inscricao — envia o comprovante/QR de inscrição em evento.

Fluxo:
1. GET /registrations?phone= → PDF do comprovante (ou 400 com lista, ou 404).
2. 404 (sem confirmada / só pendente de pagamento) → POST /registrations/link,
   manda o link do autoatendimento (ver tudo + pagar pendência).
"""
from __future__ import annotations

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import diacon_client
from app.services.deps import get_uaz_client
from app.tools.tool_modules._phone import resolve_phone


async def execute(args: dict, phone: str, db: AsyncSession) -> str:
    target_phone = resolve_phone(args.get("telefone") or args.get("phone"), phone)
    event_slug = (args.get("event_slug") or args.get("evento") or "").strip() or None

    if not target_phone:
        return "Erro: 'telefone' é obrigatório."
    if not diacon_client.is_enabled():
        return "Erro: integração Diacon não configurada."

    try:
        pdf_bytes, choice = await diacon_client.registration_pdf(
            target_phone, event_slug=event_slug
        )
    except diacon_client.DiaconError as e:
        logger.warning(f"minha_inscricao: {e.code} {e}")
        if e.code == "not_found":
            # sem inscrição confirmada, ou só pendente de pagamento → manda o link
            return await _send_link(target_phone)
        return "Não consegui buscar sua inscrição agora. Tenta de novo em alguns segundos."

    # Mais de uma inscrição confirmada → pergunta qual
    if choice:
        regs = choice.get("registrations") or choice.get("events") or []
        if regs:
            lines = ["Você tem mais de uma inscrição. Qual você quer?"]
            for r in regs:
                titulo = r.get("event_title") or r.get("title") or "evento"
                slug = r.get("event_slug") or r.get("slug")
                lines.append(f"• *{titulo}* — `{slug}`")
            lines.append("\nMe responde com o nome do evento.")
            return "\n".join(lines)
        return choice.get("message") or "Não consegui identificar a inscrição. Qual evento?"

    if not pdf_bytes:
        return "Erro: comprovante retornou vazio."

    uaz = get_uaz_client()
    try:
        await uaz.send_media_bytes(
            target_phone,
            pdf_bytes,
            mimetype="application/pdf",
            type="document",
            doc_name="comprovante.pdf",
            text="Aqui está seu comprovante 🎟️ — é só apresentar esse QR na entrada.",
        )
        return "Comprovante enviado."
    except Exception:
        logger.exception("minha_inscricao: falha ao enviar PDF via uazapi")
        return "Gerei o comprovante mas o WhatsApp recusou o envio. Tenta de novo em alguns segundos."


async def _send_link(target_phone: str) -> str:
    """Fallback: manda o link do autoatendimento (ver tudo / pagar pendência)."""
    try:
        data = await diacon_client.registration_link(target_phone)
    except diacon_client.DiaconError as e:
        logger.warning(f"minha_inscricao link: {e.code} {e}")
        return (
            "Não encontrei uma inscrição confirmada no seu número. "
            "Se você se inscreveu com outro telefone/e-mail, me avisa."
        )
    link = data.get("link")
    if not link:
        return (
            "Não encontrei uma inscrição confirmada no seu número. "
            "Quer que eu encaminhe pra equipe verificar?"
        )
    upcoming = data.get("upcoming") or []
    titulo = upcoming[0].get("event_title") if upcoming else None
    if titulo:
        return (
            f"Você tem inscrição na *{titulo}* 🎉 Toque aqui pra ver o comprovante "
            f"e o QR (e finalizar, se houver pagamento em aberto): {link}"
        )
    return f"Toque aqui pra ver suas inscrições e o QR de entrada: {link}"
