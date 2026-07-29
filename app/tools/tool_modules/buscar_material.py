"""Tool: buscar_material — envia PDF de material da igreja (lição de célula,
GAS, material de evento). A Diacon decide o acesso pelo telefone (cada material
tem a sua própria regra — a tool nunca decide).

Fluxo:
1. GET /documents/types — descobre os tipos publicados (label + aliases).
2. Casa o texto da pessoa contra label/aliases → acha o `type`.
3. GET /documents?type=&phone= → PDF (ou JSON de escolha, ou erro pastoral).
4. Envia o PDF via uazapi (base64), sem storage intermediário.
"""
from __future__ import annotations

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import diacon_client
from app.services.deps import get_uaz_client
from app.tools.tool_modules._phone import resolve_phone


def _match_type(query: str, types: list[dict]) -> dict | None:
    """Casa o texto da pessoa contra label/type/aliases (substring, sem caso)."""
    q = (query or "").lower().strip()
    if not q:
        return None
    for t in types:
        cands = [t.get("label") or "", t.get("type") or ""]
        cands += [a for a in (t.get("aliases") or []) if a]
        for c in cands:
            cl = str(c).lower().strip()
            if cl and (cl in q or q in cl):
                return t
    return None


async def execute(args: dict, phone: str, db: AsyncSession) -> str:
    target_phone = resolve_phone(args.get("telefone") or args.get("phone"), phone)
    query = (args.get("material") or args.get("assunto") or args.get("query") or "").strip()
    date = (args.get("data") or args.get("date") or "").strip() or None
    document_id = (args.get("document_id") or "").strip() or None

    if not target_phone:
        return "Erro: 'telefone' é obrigatório."
    if not diacon_client.is_enabled():
        return "Erro: integração Diacon não configurada."

    # 1+2. Descobrir o tipo (a não ser que já venha document_id de uma escolha anterior)
    doc_type = None
    if not document_id:
        try:
            data = await diacon_client.documents_types()
        except diacon_client.DiaconError as e:
            logger.warning(f"buscar_material: types {e.code} {e}")
            return "Não consegui ver os materiais agora. Tenta de novo em alguns segundos."
        types = data.get("types") or []
        matched = _match_type(query, types)
        if not matched:
            if types:
                labels = ", ".join(t.get("label") or t.get("type") or "?" for t in types)
                return f"Temos estes materiais: {labels}. Qual deles você quer?"
            return "No momento não há materiais publicados. Posso ajudar com outra coisa?"
        doc_type = matched.get("type")

    # 3. Pedir o PDF
    try:
        pdf_bytes, choice = await diacon_client.document_pdf(
            target_phone, type=doc_type, date=date, document_id=document_id
        )
    except diacon_client.DiaconError as e:
        logger.warning(f"buscar_material: documents {e.code} {e}")
        # 403 (sem acesso) / 404 (não existe) já vêm com message pastoral — repassa
        msg = str(e)
        if e.code in ("forbidden", "not_found") and msg:
            return msg
        return "Não consegui pegar o material agora. Tenta de novo em alguns segundos."

    # Escolha: mais de um material — pergunta qual
    if choice:
        options = choice.get("options") or []
        if options:
            lines = ["Encontrei mais de um. Qual você quer?"]
            for o in options:
                nome = o.get("label") or o.get("title") or "material"
                oid = o.get("document_id") or o.get("id")
                lines.append(f"• *{nome}* — ID: `{oid}`")
            lines.append("\nMe responde com o nome (ou o ID).")
            return "\n".join(lines)
        return choice.get("message") or "Não consegui identificar o material. Pode especificar?"

    if not pdf_bytes:
        return "Erro: material retornou vazio."

    uaz = get_uaz_client()
    try:
        await uaz.send_media_bytes(
            target_phone,
            pdf_bytes,
            mimetype="application/pdf",
            type="document",
            doc_name="material.pdf",
            text="Aqui está o material 📄 — bom proveito!",
        )
        return "Material enviado."
    except Exception:
        logger.exception("buscar_material: falha ao enviar PDF via uazapi")
        return "Gerei o material mas o WhatsApp recusou o envio. Tenta de novo em alguns segundos."
