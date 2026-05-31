"""Router admin — parseia prefixos de comando de números autorizados.

Prefixos suportados:
- TreinoIA12 / BaseIA12 → re-vectorização
- AgendaIA12 → CRUD de eventos
- ArquivosIA12 → gerenciar arquivos
- Resposta_oracaoIA12 → responder oração manualmente
- Limpar dados → exclusão LGPD
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from loguru import logger

from app.core.config import settings
from app.schemas.webhook import IncomingMessage


@dataclass
class AdminCommand:
    handler: str
    payload: str
    original_text: str


_PREFIXES = [
    (re.compile(r"^(TreinoIA12|BaseIA12)\s*", re.IGNORECASE), "treino"),
    (re.compile(r"^AgendaIA12\s*", re.IGNORECASE), "agenda"),
    (re.compile(r"^ArquivosIA12\s*", re.IGNORECASE), "arquivos"),
    (re.compile(r"^Resposta_oracaoIA12\s*", re.IGNORECASE), "resposta_oracao"),
    (re.compile(r"^Limpar dados\s*", re.IGNORECASE), "limpar"),
]


def is_admin(phone: str) -> bool:
    """Verifica se o telefone está na lista de admins."""
    return phone in settings.admin_phones_list


def parse_admin_command(msg: IncomingMessage) -> AdminCommand | None:
    """Tenta parsear prefixo de comando admin no texto da mensagem.

    Retorna None se não for comando admin ou se o número não for autorizado.
    """
    if not msg.text:
        return None

    if not is_admin(msg.phone):
        return None

    text = msg.text.strip()

    for pattern, handler in _PREFIXES:
        match = pattern.match(text)
        if match:
            payload = text[match.end():].strip()
            logger.bind(phone=msg.phone).info(f"Comando admin: {handler} → '{payload[:60]}'")
            return AdminCommand(
                handler=handler,
                payload=payload,
                original_text=text,
            )

    return None
