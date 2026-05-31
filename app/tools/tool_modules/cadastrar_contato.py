"""Tool: cadastrar_contato — cadastra/atualiza contato no sistema."""
from __future__ import annotations

from datetime import date

from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Contact


async def execute(
    args: dict,
    phone: str,
    db: AsyncSession,
) -> str:
    """Cadastra ou atualiza contato.

    UPSERT por telefone. Seta cadastro_completo=True.
    """
    nome = args.get("nome", "")
    telefone = args.get("telefone", phone)  # fallback para o phone da conversa
    email = args.get("email")
    status = args.get("status", "visitante")
    aniversario_str = args.get("aniversario")

    if not nome:
        return "Erro: 'nome' é obrigatório para cadastro."

    # Parse aniversário
    aniversario: date | None = None
    if aniversario_str:
        try:
            aniversario = date.fromisoformat(aniversario_str)
        except ValueError:
            logger.warning(f"Data de aniversário inválida: {aniversario_str}")

    # Buscar contato existente
    result = await db.execute(
        select(Contact).where(Contact.telefone == telefone)
    )
    contact = result.scalar_one_or_none()

    if contact:
        # Update
        contact.nome = nome
        contact.full_name = nome
        if email:
            contact.email = email
        if status:
            contact.status = status
        if aniversario:
            contact.aniversario = aniversario
        contact.cadastro_completo = True
        await db.flush()
        action = "atualizado"
    else:
        # Insert
        contact = Contact(
            telefone=telefone,
            nome=nome,
            full_name=nome,
            email=email,
            status=status,
            aniversario=aniversario,
            cadastro_completo=True,
        )
        db.add(contact)
        await db.commit()
        await db.refresh(contact)
        action = "criado"

    log = logger.bind(phone=telefone)
    log.info(f"Contato {action}: {nome} ({status})")

    parts = [f"Contato {action} com sucesso."]
    parts.append(f"Nome: {nome}")
    parts.append(f"Telefone: {telefone}")
    if email:
        parts.append(f"Email: {email}")
    if status:
        parts.append(f"Status: {status}")
    if aniversario:
        parts.append(f"Aniversário: {aniversario.strftime('%d/%m/%Y')}")
    parts.append("Cadastro completo: sim")

    return "\n".join(parts)
