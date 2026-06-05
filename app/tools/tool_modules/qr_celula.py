"""Tool: qr_celula — envia o PDF do QR de presença da célula ao líder.

Restrito: só funciona se o telefone for de líder (ou líder em treinamento).
Se a pessoa lidera mais de uma célula, devolve a lista pra escolher.
"""
from __future__ import annotations

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import diacon_client
from app.services.deps import get_uaz_client


async def execute(args: dict, phone: str, db: AsyncSession) -> str:
    target_phone = args.get("telefone") or args.get("phone") or phone
    group_id = (args.get("group_id") or args.get("celula_id") or "").strip() or None

    if not target_phone:
        return "Erro: 'telefone' é obrigatório."

    if not diacon_client.is_enabled():
        return "Erro: integração Diacon não configurada."

    try:
        pdf_bytes, ambiguity = await diacon_client.cell_qr_pdf(
            target_phone, group_id=group_id
        )
    except diacon_client.DiaconError as e:
        logger.warning(f"qr_celula: {e.code} {e}")
        if e.code == "forbidden":
            return (
                "Esse QR é só pra líderes de célula. "
                "Você ainda não consta como líder no sistema."
            )
        return "Não consegui gerar o QR agora. Tenta de novo em alguns segundos."

    # Ambiguidade: lidera mais de uma célula
    if ambiguity:
        cells = ambiguity.get("cells") or []
        lines = ["Você lidera mais de uma célula. Qual delas?"]
        for c in cells:
            lines.append(f"• *{c.get('name')}* — ID: `{c.get('group_id')}`")
        lines.append("\nMe responde com o nome da célula que quer o QR.")
        return "\n".join(lines)

    # Sucesso → envia PDF via uazapi
    if not pdf_bytes:
        return "Erro: PDF do QR retornou vazio."

    try:
        # Upload pro Drive PAES via proxy n8n (reusa fluxo de disparos)
        from app.services import drive_client

        file_id = drive_client.upload_bytes(
            content=pdf_bytes,
            filename="qr-celula.pdf",
            mimetype="application/pdf",
        )
        url = drive_client.get_public_url(file_id)

        uaz = get_uaz_client()
        await uaz.send_media(
            target_phone,
            url,
            type="document",
            doc_name="qr-celula.pdf",
            text="Aqui está o QR de presença da sua célula 📄. Imprima e cole na sala — ele é fixo, vale sempre.",
        )
        return "QR enviado ao líder."
    except Exception:
        logger.exception("Falha ao enviar QR PDF")
        return "PDF gerado mas não consegui enviar pelo WhatsApp."
