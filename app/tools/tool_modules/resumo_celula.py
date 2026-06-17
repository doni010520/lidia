"""Tool: resumo_celula — PDF do resumo de presença de um encontro da célula.

Fluxo (igual ao qr_celula):
1. Diacon devolve PDF bytes (GET /cells/summary → application/pdf)
2. uazapi recebe direto via base64

Restrito: só funciona se o telefone for líder (ou líder em treinamento).
Se a pessoa lidera mais de uma célula, devolve a lista pra escolher.
`date` opcional (YYYY-MM-DD); sem ela, usa o último encontro com check-in.
"""
from __future__ import annotations

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import diacon_client
from app.services.deps import get_uaz_client


async def execute(args: dict, phone: str, db: AsyncSession) -> str:
    target_phone = args.get("telefone") or args.get("phone") or phone
    group_id = (args.get("group_id") or args.get("celula_id") or "").strip() or None
    date = (args.get("data") or args.get("date") or "").strip() or None

    if not target_phone:
        return "Erro: 'telefone' é obrigatório."

    if not diacon_client.is_enabled():
        return "Erro: integração Diacon não configurada."

    try:
        pdf_bytes, ambiguity = await diacon_client.cells_summary_pdf(
            target_phone, group_id=group_id, date=date
        )
    except diacon_client.DiaconError as e:
        logger.warning(f"resumo_celula: {e.code} {e}")
        if e.code == "forbidden":
            return (
                "Esse resumo é só pra líderes de célula. "
                "Você ainda não consta como líder no sistema."
            )
        if e.code == "not_found":
            return (
                "Não achei nenhum encontro com presença registrada"
                + (f" em {date}" if date else "")
                + ". Confere a data ou registra a presença primeiro."
            )
        return "Não consegui gerar o resumo agora. Tenta de novo em alguns segundos."

    # Ambiguidade: lidera mais de uma célula
    if ambiguity:
        cells = ambiguity.get("cells") or []
        lines = ["Você lidera mais de uma célula. De qual quer o resumo?"]
        for c in cells:
            lines.append(f"• *{c.get('name')}* — ID: `{c.get('group_id')}`")
        lines.append("\nMe responde com o nome da célula.")
        return "\n".join(lines)

    if not pdf_bytes:
        return "Erro: PDF do resumo retornou vazio."

    uaz = get_uaz_client()
    try:
        await uaz.send_media_bytes(
            target_phone,
            pdf_bytes,
            mimetype="application/pdf",
            type="document",
            doc_name="resumo-celula.pdf",
            text="Aqui está o resumo de presença do encontro da sua célula 📄",
        )
        return "Resumo enviado ao líder."
    except Exception:
        logger.exception("Falha ao enviar resumo PDF via uazapi (base64)")
        return "Gerei o PDF mas o WhatsApp recusou o envio. Tenta de novo em alguns segundos."
