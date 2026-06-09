"""Worker: aniversarios — diario 8h BR (portado de kwHB5pFbjQbtSsps)."""
from __future__ import annotations
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
import openai
from loguru import logger
from sqlalchemy import select, text
from app.core.config import settings
from app.db import async_session_factory
from app.models.liderancas import PastorAniversario
from app.services.deps import get_uaz_client

_SP_TZ = ZoneInfo("America/Sao_Paulo")

_PROMPT_INDIVIDUAL = """Voce e LidIA, assistente virtual da PAES.
Gere mensagem CURTA e calorosa de parabens para {nome}.

Regras:
- Tom acolhedor, sem exagero. Emojis com moderacao.
- Mencione bencao/oracao.
- Maximo 4 linhas.
- Use o nome do aniversariante.
"""

_PROMPT_RELATORIO = """Hoje e: {data_atual_br}

Voce prepara relatorio diario de aniversariantes para os pastores.

Lista:
{lista}

Gere mensagem formatada EXATAMENTE assim (copie os dados acima sem alterar numeros nem links):
*Relatorio de Aniversariantes - [data]*
Paz do Senhor!
Hoje temos N aniversariante(s):
1. Nome - Telefone: (XX) XXXXX-XXXX
   wa.me/XXXXXXXXXXX

Sugestao: enviar bencao pessoal.
"""

async def _fetch_aniversariantes() -> list[dict]:
    """Fase 4: Diacon é a fonte. GET /birthdays?range=today.

    Fallback: Postgres local (caso Diacon esteja fora).
    """
    from app.services import diacon_client

    if diacon_client.is_enabled():
        try:
            data = await diacon_client.birthdays("today")
            return [
                {
                    "id": b.get("id"),
                    "telefone": (b.get("phone") or "").lstrip("+"),
                    "nome": b.get("first_name") or b.get("full_name"),
                    "email": None,
                }
                for b in (data.get("birthdays") or [])
                if b.get("allow_contact", True) and b.get("phone")
            ]
        except Exception:
            logger.exception("aniversarios: Diacon falhou, fallback local")

    # Fallback local
    async with async_session_factory() as db:
        result = await db.execute(text("""
            SELECT id, telefone, COALESCE(full_name, nome) AS nome, email
            FROM contacts
            WHERE aniversario IS NOT NULL
              AND TO_CHAR(aniversario, 'MM-DD') = TO_CHAR(CURRENT_DATE, 'MM-DD')
              AND is_blocked = FALSE
              AND telefone IS NOT NULL AND telefone <> ''
        """))
        return [{"id": r.id, "telefone": r.telefone, "nome": r.nome, "email": r.email}
                for r in result.fetchall()]

async def _fetch_pastores() -> list[dict]:
    async with async_session_factory() as db:
        result = await db.execute(select(PastorAniversario))
        return [{"id": p.id, "nome": p.nome, "telefone": p.telefone}
                for p in result.scalars().all() if p.telefone]

async def _gerar_mensagem_individual(nome: str, client: openai.AsyncOpenAI) -> str:
    resp = await client.chat.completions.create(
        model=settings.openai_model, temperature=0.7, max_tokens=300,
        messages=[
            {"role": "system", "content": _PROMPT_INDIVIDUAL.format(nome=nome)},
            {"role": "user", "content": f"Gere a mensagem de aniversario para {nome}."},
        ],
    )
    return (resp.choices[0].message.content or "").strip()

def _format_phone(raw: str) -> tuple[str, str]:
    """Retorna (telefone_local, link_wame) a partir do número bruto.

    Exemplos:
        '5581999998888' → ('(81) 99999-8888', 'wa.me/5581999998888')
        '81999998888'   → ('(81) 99999-8888', 'wa.me/5581999998888')
    """
    digits = raw.lstrip("+").strip()
    # Garante o 55 pro link wa.me
    full = digits if digits.startswith("55") else f"55{digits}"
    # Remove o 55 pro display local
    local = digits[2:] if digits.startswith("55") else digits
    # Formata (XX) XXXXX-XXXX se tiver 11 dígitos
    if len(local) == 11:
        display = f"({local[:2]}) {local[2:7]}-{local[7:]}"
    elif len(local) == 10:
        display = f"({local[:2]}) {local[2:6]}-{local[6:]}"
    else:
        display = local
    return display, f"wa.me/{full}"


async def _gerar_relatorio_pastores(aniversariantes: list[dict], client: openai.AsyncOpenAI) -> str:
    if not aniversariantes:
        return ""
    items = []
    for i, a in enumerate(aniversariantes):
        display, wame = _format_phone(a.get("telefone") or "")
        items.append(
            f"{i+1}. {a['nome']}\n   - Telefone: {display}\n   - {wame}"
        )
    lista = "\n\n".join(items)
    data_br = datetime.now(_SP_TZ).strftime("%d de %B de %Y")
    prompt = _PROMPT_RELATORIO.format(data_atual_br=data_br, lista=lista)
    resp = await client.chat.completions.create(
        model=settings.openai_model, temperature=0.3, max_tokens=800,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": "Gere o relatorio consolidado."},
        ],
    )
    return (resp.choices[0].message.content or "").strip()

async def check_aniversariantes() -> dict[str, int]:
    aniversariantes = await _fetch_aniversariantes()
    if not aniversariantes:
        logger.info("Sem aniversariantes hoje.")
        return {"aniversariantes": 0, "mensagens_enviadas": 0, "pastores_avisados": 0}
    logger.info(f"{len(aniversariantes)} aniversariante(s) hoje.")
    uaz = get_uaz_client()
    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
    enviadas = 0
    for a in aniversariantes:
        try:
            msg = await _gerar_mensagem_individual(a["nome"] or "amigo(a)", client)
            await uaz.send_text(a["telefone"], msg, delay=3000)
            enviadas += 1
            await asyncio.sleep(3)
        except Exception:
            logger.exception(f"Falha ao parabenizar {a['telefone']}")
    pastores = await _fetch_pastores()
    pastores_avisados = 0
    if pastores:
        relatorio = await _gerar_relatorio_pastores(aniversariantes, client)
        if relatorio:
            for p in pastores:
                try:
                    msg = f"Paz, {p['nome'] or 'pastor(a)'}!\n\n{relatorio}"
                    await uaz.send_text(p["telefone"], msg, delay=3000)
                    pastores_avisados += 1
                    await asyncio.sleep(3)
                except Exception:
                    logger.exception(f"Falha ao avisar pastor {p['telefone']}")
    return {"aniversariantes": len(aniversariantes), "mensagens_enviadas": enviadas, "pastores_avisados": pastores_avisados}
