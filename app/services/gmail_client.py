"""Cliente Gmail.

Estratégia:
- Se `N8N_GOOGLE_WEBHOOK_URL` estiver setado → envio via n8n proxy.
- Caso contrário → fallback para Service Account local (gmail.send + DWD).
"""
from __future__ import annotations

import base64
from email.mime.text import MIMEText
from pathlib import Path

from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.services import n8n_google_proxy

_service = None


def _get_service():
    global _service
    if _service is not None:
        return _service

    sa_path = Path(settings.gmail_service_account_json)
    if not sa_path.exists():
        logger.warning(f"Gmail service account não encontrada: {sa_path}")
        return None

    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_service_account_file(
        str(sa_path),
        scopes=["https://www.googleapis.com/auth/gmail.send"],
        subject=settings.gmail_from,
    )
    _service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    logger.info("Gmail client inicializado (SA local)")
    return _service


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
def send_email(
    to: str,
    subject: str,
    body: str,
) -> dict:
    """Envia email."""
    if n8n_google_proxy.is_enabled():
        try:
            result = n8n_google_proxy.call(
                "gmail.send",
                {
                    "to": to,
                    "subject": subject,
                    "body": body,
                    "from": settings.gmail_from,
                },
            )
            logger.debug(f"Email enviado (n8n) para {to}: {subject}")
            return result if isinstance(result, dict) else {"id": str(result)}
        except Exception as e:
            logger.warning(f"Proxy n8n falhou em gmail.send: {e}")
            return {}

    service = _get_service()
    if service is None:
        logger.warning("Gmail client não disponível, email não enviado")
        return {}

    msg = MIMEText(body, "plain", "utf-8")
    msg["to"] = to
    msg["from"] = settings.gmail_from
    msg["subject"] = subject

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    result = service.users().messages().send(
        userId="me",
        body={"raw": raw},
    ).execute()

    logger.debug(f"Email enviado para {to}: {subject}")
    return result
