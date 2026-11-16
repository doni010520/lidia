"""Cliente Zernio (WhatsApp Business com coexistência / API Oficial).

Mesma interface do UAZClient: o resto da LidIA chama `get_uaz_client()` e não
sabe qual canal está ativo (settings.whatsapp_provider).

Diferenças de canal que ficam aqui dentro:
- Envio sempre por `POST /inbox/conversations` (cria ou reaproveita a conversa
  com o número). Fora da janela de 24h a Meta recusa texto livre: só template.
- Mídia vai por URL pública. Bytes (PDFs da Diacon) são publicados num link
  temporário da própria LidIA (media_temp) e a Zernio busca de lá.
- Mídia recebida vem por URL autenticada que expira: baixar logo, com o token.
- Sem "digitando", sem conferência de número, sem configurações de chatbot.
"""
from __future__ import annotations

import uuid
from typing import Any, Literal

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings

_TIPO = {"image": "image", "video": "video", "audio": "audio", "ptt": "audio",
         "document": "file", "sticker": "image"}


class ZernioError(RuntimeError):
    pass


class ZernioClient:
    def __init__(self) -> None:
        self.base_url = settings.zernio_base_url.rstrip("/")
        self.account_id = settings.zernio_account_id
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {settings.zernio_api_key}"},
            timeout=60.0,
        )

    async def _req(self, method: str, path: str, *, json: dict | None = None,
                   params: dict | None = None, idem: str | None = None) -> dict:
        if settings.dry_run:
            logger.info(f"[DRY_RUN] Zernio {method} {path} → {json}")
            return {"dry_run": True}
        headers = {"Idempotency-Key": idem} if idem else None
        resp = await self.client.request(method, path, json=json, params=params, headers=headers)
        if resp.status_code >= 400:
            raise ZernioError(f"Zernio {method} {path} → {resp.status_code}: {resp.text[:400]}")
        return resp.json() if resp.content else {}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    async def _post_conversa(self, payload: dict, idem: str) -> dict:
        return await self._req("POST", "/inbox/conversations", json=payload, idem=idem)

    async def _conta(self) -> str:
        """Id da conta WhatsApp. Sem ZERNIO_ACCOUNT_ID, descobre pela conta
        WhatsApp ativa do perfil da PAES: assim a LidIA passa a funcionar no
        instante em que o número é conectado, sem mexer em configuração."""
        if self.account_id:
            return self.account_id
        import time
        if time.monotonic() < getattr(self, "_proxima_busca", 0):
            raise ZernioError("Nenhuma conta WhatsApp conectada no perfil da Zernio")
        r = await self._req("GET", "/accounts", params={"profileId": settings.zernio_profile_id})
        contas = [a for a in r.get("accounts", []) if a.get("platform") == "whatsapp" and a.get("isActive")]
        if not contas:
            self._proxima_busca = time.monotonic() + 60
            raise ZernioError("Nenhuma conta WhatsApp conectada no perfil da Zernio")
        self.account_id = contas[0]["_id"]
        logger.info(f"Zernio: conta WhatsApp {self.account_id} ({contas[0].get('username')})")
        return self.account_id

    async def _send(self, number: str, body: dict[str, Any]) -> dict:
        """Envia para o número; a mesma Idempotency-Key em todas as tentativas
        evita mensagem duplicada quando a 1ª chegou mas a resposta se perdeu."""
        idem = body.pop("_idem", None) or str(uuid.uuid4())
        payload = {"accountId": await self._conta(), "participantId": _so_digitos(number), **body}
        r = await self._post_conversa(payload, idem)
        data = r.get("data") or r
        # Mesmo formato que o resto do código já lê da uazapi
        return {**data, "messageid": data.get("messageId"), "chatid": number}

    # ── Envio ────────────────────────────────────────────────

    async def send_text(self, number: str, text: str, *, link_preview: bool = False,
                        reply_id: str | None = None, **_: Any) -> dict:
        body: dict[str, Any] = {"message": text, "linkPreview": link_preview,
                                "_idem": str(uuid.uuid4())}
        if reply_id:
            body["replyTo"] = reply_id
        return await self._send(number, body)

    async def send_media(self, number: str, file: str,
                         type: Literal["image", "document", "video", "audio", "ptt", "sticker"],
                         *, text: str | None = None, doc_name: str | None = None,
                         reply_id: str | None = None, **_: Any) -> dict:
        if file.startswith("data:"):
            # Base64 embutido (padrão da uazapi): publica e manda o link.
            import base64
            head, b64 = file.split(",", 1)
            mimetype = head[5:].split(";")[0]
            return await self.send_media_bytes(number, base64.b64decode(b64), mimetype, type,
                                               text=text, doc_name=doc_name)
        body: dict[str, Any] = {"attachmentUrl": file, "attachmentType": _TIPO.get(type, "file"),
                                "_idem": str(uuid.uuid4())}
        if text:
            body["message"] = text
        if doc_name and type == "document":
            body["attachmentName"] = doc_name
        if type == "ptt":
            body["voiceNote"] = True
        if reply_id:
            body["replyTo"] = reply_id
        return await self._send(number, body)

    async def send_media_bytes(self, number: str, content: bytes, mimetype: str,
                               type: Literal["image", "document", "video", "audio", "ptt", "sticker"],
                               *, text: str | None = None, doc_name: str | None = None,
                               **_: Any) -> dict:
        from app.services import media_temp
        url = await media_temp.publicar(content, mimetype, doc_name)
        return await self.send_media(number, url, type, text=text, doc_name=doc_name)

    async def send_buttons(self, number: str, text: str, buttons: list[tuple[str, str]]) -> dict:
        """Botões de resposta (máx. 3). O clique volta no webhook com o id."""
        body = {"message": text, "_idem": str(uuid.uuid4()),
                "buttons": [{"type": "postback", "title": t[:20], "payload": i} for t, i in buttons[:3]]}
        return await self._send(number, body)

    async def send_contact(self, number: str, full_name: str, phone_number: str,
                           *, organization: str | None = None, **_: Any) -> dict:
        contato: dict[str, Any] = {
            "name": {"formatted_name": full_name, "first_name": full_name.split(" ")[0]},
            "phones": [{"phone": p.strip(), "type": "CELL"} for p in phone_number.split(",") if p.strip()],
        }
        if organization:
            contato["org"] = {"company": organization}
        return await self._send(number, {"contacts": [contato], "_idem": str(uuid.uuid4())})

    async def send_template(self, number: str, name: str, language: str = "pt_BR",
                            components: list[dict] | None = None) -> dict:
        """Única forma de iniciar conversa fora da janela de 24h."""
        el: dict[str, Any] = {"name": name, "language": language}
        if components:
            el["components"] = components
        return await self._send(number, {"template": {"elements": [el]}, "_idem": str(uuid.uuid4())})

    # ── Recebimento ──────────────────────────────────────────

    async def download_message(self, message_id: str, *, media_url: str | None = None,
                               transcribe: bool = False, **_: Any) -> dict:
        """Baixa a mídia pela URL do webhook. Devolve no formato da uazapi
        ({'file': base64, 'transcription'?}) pro media_processor não mudar."""
        import base64
        if not media_url:
            raise ZernioError(f"Mídia {message_id} sem URL")
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as c:
            auth = {"Authorization": f"Bearer {settings.zernio_api_key}"} if "zernio" in media_url else {}
            resp = await c.get(media_url, headers=auth)
            resp.raise_for_status()
        out: dict[str, Any] = {"file": base64.b64encode(resp.content).decode("ascii"),
                               "mimetype": resp.headers.get("content-type", "")}
        if transcribe:
            out["transcription"] = await _transcrever(resp.content, out["mimetype"])
        return out

    # ── Recursos que só existiam na uazapi ───────────────────

    async def send_presence(self, *_: Any, **__: Any) -> dict:
        return {}

    async def update_chatbot_settings(self, *_: Any, **__: Any) -> dict:
        return {}

    async def mark_read(self, *_: Any, **__: Any) -> dict:
        return {}

    async def react(self, *_: Any, **__: Any) -> dict:
        return {}

    async def check_number(self, numbers: list[str]) -> list[dict]:
        # A API Oficial resolve o número na entrega; não há consulta prévia.
        return [{"query": n, "isInWhatsapp": True, "jid": f"{_so_digitos(n)}@s.whatsapp.net"}
                for n in numbers]

    async def close(self) -> None:
        await self.client.aclose()


def _so_digitos(n: str) -> str:
    return "".join(ch for ch in str(n).split("@")[0] if ch.isdigit())


async def _transcrever(content: bytes, mimetype: str) -> str:
    """Áudio → texto com o Whisper da OpenAI (na uazapi isso era embutido)."""
    import openai
    ext = "ogg" if "ogg" in mimetype or "opus" in mimetype else (mimetype.split("/")[-1] or "ogg")
    try:
        client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
        r = await client.audio.transcriptions.create(
            model="whisper-1", file=(f"audio.{ext}", content), language="pt",
        )
        return r.text or ""
    except Exception:
        logger.exception("Zernio: falha na transcrição do áudio")
        return ""
