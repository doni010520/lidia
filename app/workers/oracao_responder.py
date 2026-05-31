"""Worker: oracao_responder — poll Sheets de oração, envia respostas.

Roda a cada 5min via APScheduler. Lê planilha de oração:
- Se linha tem coluna "Resposta" preenchida e "Enviado" == "false":
  - Monta mensagem com encorajamento + resposta
  - Envia via uazapi
  - Marca "Enviado" = "true"
"""
from __future__ import annotations

import openai
from loguru import logger

from app.core.config import settings
from app.services import sheets_client
from app.services.deps import get_uaz_client

SYSTEM_PROMPT = """Persona: Você é LidIA, uma assistente virtual atenciosa e encorajadora do time de intercessão. Sua comunicação deve ser sempre clara, positiva e reconfortante.

Objetivo: Informar ao usuário que o pedido de intercessão dele foi concluído pela equipe.

Mensagem de encorajamento: {encorajamento}

Instruções:
Verifique se há uma mensagem de encorajamento da equipe.

Cenário A: Existe uma mensagem de encorajamento.
Use o seguinte texto como base:
"A paz! Informamos que a sua intercessão foi realizada pela nossa equipe pastoral. A equipe também deixou uma palavra de encorajamento para você: {encorajamento}. Continuamos orando por você. Que Deus abençoe!"

Cenário B: Não há encorajamento (campo vazio ou 'sem palavra de encorajamento').
Texto simples: "A paz! Informamos que sua intercessão foi realizada pela nossa equipe pastoral. Continuamos orando por você. 🙏"

Sempre mantenha o tom acolhedor e esperançoso."""


async def check_and_send() -> int:
    """Verifica planilha de oração e envia respostas pendentes."""
    sheet_id = settings.sheets_log_oracao_id
    if not sheet_id:
        return 0

    try:
        rows = sheets_client.read_all(sheet_id)
    except Exception:
        logger.exception("Erro ao ler Sheets de oração")
        return 0

    if not rows:
        return 0

    uaz = get_uaz_client()
    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
    sent_count = 0

    for row in rows:
        resposta = row.get("Resposta", "").strip()
        enviado = row.get("Enviado", "").strip().lower()
        nome = row.get("Nome", "")
        telefone = row.get("Telefone", "")
        encorajamento = row.get("Encorajamento", "sem palavra de encorajamento")
        row_num = row.get("_row_number", 0)

        # Pular se sem resposta ou já enviado
        if not resposta or enviado == "true" or not telefone:
            continue

        # Gerar mensagem via LLM
        try:
            system = SYSTEM_PROMPT.replace("{encorajamento}", encorajamento)
            response = await client.chat.completions.create(
                model=settings.openai_model,
                temperature=0.5,
                max_tokens=500,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": f"meu nome é: {nome}"},
                ],
            )
            msg_text = response.choices[0].message.content or ""
        except Exception:
            logger.exception(f"Erro ao gerar resposta de oração para {nome}")
            continue

        if not msg_text:
            continue

        # Enviar
        try:
            await uaz.send_text(telefone, msg_text)
            sent_count += 1
            logger.info(f"Resposta de oração enviada para {nome} ({telefone})")
        except Exception:
            logger.exception(f"Erro ao enviar resposta de oração para {telefone}")
            continue

        # Marcar como enviado no Sheets
        if row_num:
            try:
                sheets_client.update_cell(
                    sheet_id,
                    f"F{row_num}",  # Coluna F = Enviado
                    "true",
                )
            except Exception:
                logger.exception(f"Erro ao marcar oração como enviada (linha {row_num})")

    if sent_count:
        logger.info(f"Orações respondidas: {sent_count}")
    return sent_count
