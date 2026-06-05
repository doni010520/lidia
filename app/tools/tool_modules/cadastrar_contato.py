"""Tool: cadastrar_contato — cadastra ou atualiza membro no Diacon.

Fase 3: Diacon = fonte de verdade. Mantemos um write-behind local em
`contacts` (atualizado se existir) só pra debounce e logs imediatos —
não é fonte de verdade.
"""
from __future__ import annotations

from datetime import date

from loguru import logger
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Contact
from app.services import diacon_client


def _map_status_to_diacon(status: str) -> str:
    """Nossos status ('membro', 'visitante') para Diacon ('active', 'visitor')."""
    s = (status or "").lower().strip()
    if s in ("membro", "member", "active"):
        return "active"
    if s in ("visitante", "visitor"):
        return "visitor"
    if s in ("inativo", "inactive"):
        return "inactive"
    if s in ("pendente", "pending"):
        return "pending"
    return "active"


async def execute(args: dict, phone: str, db: AsyncSession) -> str:
    nome = (args.get("nome") or "").strip()
    telefone = args.get("telefone") or phone
    email = args.get("email")
    status_raw = args.get("status") or "visitante"
    aniversario_str = args.get("aniversario")

    if not nome:
        return "Erro: 'nome' é obrigatório para cadastro."

    if not diacon_client.is_enabled():
        return "Erro: integração Diacon não configurada."

    # Validar aniversário
    birth_date = None
    if aniversario_str:
        try:
            birth_date = str(date.fromisoformat(str(aniversario_str)[:10]))
        except Exception:
            return f"Erro: data de aniversário '{aniversario_str}' inválida (use YYYY-MM-DD)."

    diacon_status = _map_status_to_diacon(status_raw)

    # ── Tentar criar no Diacon (idempotente por phone) ──
    try:
        resp = await diacon_client.member_create(
            full_name=nome,
            phone=telefone,
            email=email,
            birth_date=birth_date,
            status=diacon_status,
        )
    except diacon_client.DiaconError as e:
        logger.warning(f"cadastrar_contato: Diacon {e.code} {e}")
        return f"Não consegui cadastrar agora ({e.code or 'erro'}). Tenta de novo em alguns segundos."

    member = resp.get("member") or {}
    created = resp.get("created", False)

    # ── Write-behind no Postgres local (apenas pra debounce/logs) ──
    try:
        await db.execute(
            update(Contact)
            .where(Contact.telefone == telefone)
            .values(
                nome=member.get("first_name") or nome.split()[0] if nome else None,
                full_name=member.get("full_name") or nome,
                email=email,
                status=status_raw,
                aniversario=date.fromisoformat(birth_date) if birth_date else None,
                cadastro_completo=True,
            )
        )
        await db.commit()
    except Exception:
        logger.exception("cadastrar_contato: write-behind local falhou (não crítico)")

    first = member.get("first_name") or nome.split()[0] if nome else ""
    if created:
        return f"Cadastro feito com sucesso, {first}! 🎉 Seja bem-vindo(a) à família PAES."
    return f"Tudo certo, {first}! Seu cadastro está atualizado."
