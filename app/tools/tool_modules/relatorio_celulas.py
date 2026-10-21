"""Tool: relatorio_celulas — relatório de encontros de um PERÍODO (Diacon 7b).

GET /cells/report. Vale pra líder, supervisor e coordenador (estes recebem as
células abaixo deles). Diferente do resumo_celula, que é UM encontro em PDF.

- Texto (padrão): a Diacon devolve `text` pronto, sem nomes de ninguém.
- PDF (`formato="pdf"`): só quando a pessoa pede PDF/arquivo ou os NOMES de
  quem veio. Nomes só de membros com consentimento; máx. 90 dias; 5 PDFs/hora.
"""
from __future__ import annotations

import re

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import diacon_client
from app.services.deps import get_uaz_client
from app.tools.tool_modules._phone import resolve_phone

LEGENDA_PDF = (
    "Aqui está o relatório de encontros 📄. Os nomes são de quem autorizou o uso "
    "dos dados — é para o cuidado da célula, não para repassar."
)


def _periodo(args: dict) -> dict:
    """Converte os args do modelo nos parâmetros da Diacon (só UM período)."""
    mes = str(args.get("mes") or "").strip().lower()
    de = str(args.get("de") or "").strip()
    ate = str(args.get("ate") or "").strip()
    dias = args.get("dias")
    if de and ate:
        return {"de": de, "ate": ate}
    if mes in ("este_mes", "mes_passado") or re.fullmatch(r"\d{4}-\d{2}", mes):
        return {"mes": mes}
    try:
        if dias and int(dias) > 0:
            return {"dias": int(dias)}
    except (TypeError, ValueError):
        pass
    return {}  # Diacon usa os últimos 60 dias


async def execute(args: dict, phone: str, db: AsyncSession) -> str:
    target_phone = resolve_phone(args.get("telefone") or args.get("phone"), phone)
    if not target_phone:
        return "Erro: 'telefone' é obrigatório."
    if not diacon_client.is_enabled():
        return "Erro: integração Diacon não configurada."

    periodo = _periodo(args)
    celula = (args.get("celula") or "").strip() or None
    pdf = str(args.get("formato") or "").strip().lower() == "pdf"

    try:
        data, pdf_bytes = await diacon_client.cells_report(
            target_phone, periodo=periodo, celula=celula, pdf=pdf
        )
    except diacon_client.DiaconError as e:
        logger.warning(f"relatorio_celulas: {e.status} {e.code} {e}")
        if e.status == 403 or e.code == "forbidden":
            return (
                "Esse relatório é para quem lidera célula, supervisão ou coordenação, "
                "e você ainda não consta assim no sistema. Se for o caso, a secretaria "
                "consegue atualizar o seu cadastro."
            )
        if e.status == 429:
            return (
                "Você já recebeu 5 relatórios em PDF na última hora, que é o limite. "
                "Posso te mandar agora em texto, ou o PDF daqui a pouco."
            )
        if e.status == 400:
            return f"A Diacon não aceitou esse pedido: {e}"
        return "Não consegui gerar o relatório agora. Tenta de novo em alguns segundos."

    # Nome da célula não casou → mostrar as opções
    if data and data.get("celulas") and not data.get("ok", True):
        nomes = [c.get("nome") or c.get("name") for c in data["celulas"]]
        lista = "\n".join(f"• {n}" for n in nomes if n)
        return (
            "Não achei essa célula entre as suas. As que você acompanha são:\n"
            f"{lista}\n\nDe qual quer o relatório?"
        )

    if pdf:
        if not pdf_bytes:
            return "Erro: o PDF do relatório veio vazio."
        try:
            await get_uaz_client().send_media_bytes(
                target_phone, pdf_bytes, mimetype="application/pdf", type="document",
                doc_name="relatorio-encontros.pdf", text=LEGENDA_PDF,
            )
            return "Relatório em PDF enviado."
        except Exception:
            logger.exception("relatorio_celulas: falha ao enviar PDF")
            return "Gerei o PDF mas o WhatsApp recusou o envio. Tenta de novo em alguns segundos."

    texto = (data or {}).get("text") or ""
    if not texto:
        return "A Diacon não devolveu o relatório. Tenta de novo em alguns segundos."
    return (
        "Envie o relatório abaixo para a pessoa EXATAMENTE como está, sem resumir, "
        "sem tirar linhas e sem acrescentar números:\n\n" + texto
    )
