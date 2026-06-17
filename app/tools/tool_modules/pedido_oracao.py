"""Tool: pedido_oracao — pedido pessoal pra fila pastoral (Céus Abertos).

Distingue-se de `oracao_do_dia` (oração corporativa pelo motivo do dia).

Use quando a pessoa quer que ALGUÉM ore POR ELA ou alguém querido.
Gravado em /oracao/pedido (Diacon = fila pastoral) E notifica os líderes
do ministério de Oração por WhatsApp (telefones em equipes_responsaveis).
"""
from __future__ import annotations

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.equipes import EquipeResponsavel
from app.services import diacon_client
from app.services.deps import get_uaz_client


def _format_phone(raw: str) -> tuple[str, str]:
    """Retorna (telefone_display, link_wame) a partir do número bruto."""
    digits = (raw or "").lstrip("+").strip()
    full = digits if digits.startswith("55") else f"55{digits}"
    local = digits[2:] if digits.startswith("55") else digits
    if len(local) == 11:
        display = f"({local[:2]}) {local[2:7]}-{local[7:]}"
    elif len(local) == 10:
        display = f"({local[:2]}) {local[2:6]}-{local[6:]}"
    else:
        display = local or digits
    return display, f"wa.me/{full}"


async def _notificar_lideres(
    db: AsyncSession, *, nome: str, telefone: str, pedido: str
) -> int:
    """Envia o pedido de oração para os líderes da equipe Oração.

    Best-effort: nunca levanta exceção pro fluxo principal.
    """
    try:
        result = await db.execute(
            select(EquipeResponsavel).where(
                EquipeResponsavel.equipe.ilike("%Oração%")
            )
        )
        equipe = result.scalar_one_or_none()
    except Exception:
        logger.exception("pedido_oracao: falha ao buscar equipe Oração")
        return 0

    telefones = list(getattr(equipe, "telefones_responsaveis", None) or []) if equipe else []
    if not telefones:
        logger.warning("pedido_oracao: equipe Oração sem telefones_responsaveis configurados")
        return 0

    display, wame = _format_phone(telefone)
    nome_label = nome or "Não informado"
    msg = (
        "🙏 *Novo pedido de oração*\n\n"
        f"*De:* {nome_label}\n"
        f"*Contato:* {display} ({wame})\n\n"
        f"*Pedido:*\n{pedido}\n\n"
        "_Registrado na fila Céus Abertos (painel Diacon). "
        "Toque no link do contato para responder a pessoa diretamente._"
    )

    uaz = get_uaz_client()
    enviados = 0
    for tel_lider in telefones:
        tel_lider = (tel_lider or "").strip()
        if not tel_lider:
            continue
        try:
            await uaz.send_text(tel_lider, msg, delay=1000)
            enviados += 1
        except Exception:
            logger.exception(f"pedido_oracao: falha ao notificar líder {tel_lider}")
    if enviados:
        logger.bind(phone=telefone).info(
            f"pedido_oracao: {enviados} líder(es) de oração notificado(s)"
        )
    return enviados


async def execute(args: dict, phone: str, db: AsyncSession) -> str:
    pedido = (args.get("pedido") or args.get("request") or "").strip()
    nome = (args.get("nome") or args.get("name") or "").strip()
    tel = args.get("telefone") or args.get("phone") or phone

    if len(pedido) < 2:
        return "Erro: 'pedido' precisa ter pelo menos 2 caracteres."

    if not diacon_client.is_enabled():
        return "Erro: integração Diacon não configurada."

    # ── 1. Registra na fila pastoral (Diacon = fonte de verdade) ──
    try:
        data = await diacon_client.oracao_pedido(
            request=pedido[:2000], phone=tel, name=nome or None
        )
    except diacon_client.DiaconError as e:
        logger.warning(f"pedido_oracao: {e.code} {e}")
        return "Não consegui registrar o pedido agora. Tenta de novo em alguns segundos."

    logger.bind(phone=tel).info(
        f"Pedido de oração registrado em Diacon: id={data.get('id')}"
    )

    # ── 2. Notifica os líderes do ministério de Oração (best-effort) ──
    await _notificar_lideres(db, nome=nome, telefone=tel, pedido=pedido[:2000])

    return (
        "🙏 Seu pedido foi registrado e a equipe pastoral foi avisada. "
        "Estamos orando por você. Que a paz de Cristo te console."
    )
