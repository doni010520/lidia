from __future__ import annotations

from typing import Any, Literal

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings


class UAZClient:
    """Cliente HTTP para a API uazapi v2."""

    def __init__(self) -> None:
        self.base_url = settings.uaz_base_url.rstrip("/")
        self.token = settings.uaz_token
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"token": self.token, "Content-Type": "application/json"},
            timeout=30.0,
        )

    # ── helpers ──────────────────────────────────────────────

    async def _post(self, path: str, payload: dict[str, Any]) -> dict:
        if settings.dry_run:
            logger.info(f"[DRY_RUN] POST {path} → {payload}")
            return {"dry_run": True}
        resp = await self.client.post(path, json=payload)
        resp.raise_for_status()
        return resp.json()

    # ── Envio de mensagens ───────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    async def send_text(
        self,
        number: str,
        text: str,
        *,
        link_preview: bool = False,
        reply_id: str | None = None,
        mentions: str = "",
        read_chat: bool = True,
        delay: int = 0,
    ) -> dict:
        payload: dict[str, Any] = {
            "number": number,
            "text": text,
            "linkPreview": link_preview,
            "readChat": read_chat,
            "delay": delay,
        }
        if reply_id:
            payload["replyid"] = reply_id
        if mentions:
            payload["mentions"] = mentions
        return await self._post("/send/text", payload)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    async def send_media(
        self,
        number: str,
        file: str,
        type: Literal["image", "document", "video", "audio", "ptt", "sticker"],
        *,
        text: str | None = None,
        doc_name: str | None = None,
        reply_id: str | None = None,
        mentions: str = "",
        read_chat: bool = True,
        delay: int = 0,
    ) -> dict:
        payload: dict[str, Any] = {
            "number": number,
            "file": file,
            "type": type,
            "readChat": read_chat,
            "delay": delay,
        }
        if text:
            payload["text"] = text
        if doc_name:
            payload["docName"] = doc_name
        if reply_id:
            payload["replyid"] = reply_id
        if mentions:
            payload["mentions"] = mentions
        return await self._post("/send/media", payload)

    async def send_presence(
        self,
        number: str,
        presence: Literal["composing", "recording"] = "composing",
        delay: int = 2000,
    ) -> dict:
        return await self._post("/message/presence", {
            "number": number,
            "presence": presence,
            "delay": delay,
        })

    # ── Ações em mensagens ───────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    async def download_message(
        self,
        message_id: str,
        *,
        transcribe: bool = False,
        openai_apikey: str | None = None,
    ) -> dict:
        payload: dict[str, Any] = {"id": message_id}
        if transcribe:
            payload["transcribe"] = True
            if openai_apikey:
                payload["openai_apikey"] = openai_apikey
        return await self._post("/message/download", payload)

    async def react(self, number: str, text: str, message_id: str) -> dict:
        return await self._post("/message/react", {
            "number": number,
            "text": text,
            "id": message_id,
        })

    async def mark_read(self, message_ids: list[str]) -> dict:
        return await self._post("/message/markread", {"id": message_ids})

    async def find_messages(
        self,
        chatid: str | None = None,
        message_id: str | None = None,
        limit: int = 2,
    ) -> dict:
        payload: dict[str, Any] = {"limit": limit}
        if chatid:
            payload["chatid"] = chatid
        if message_id:
            payload["id"] = message_id
        return await self._post("/message/find", payload)

    # ── Chats / Leads ────────────────────────────────────────

    async def edit_lead(self, id: str, **lead_fields: Any) -> dict:
        payload: dict[str, Any] = {"id": id, **lead_fields}
        return await self._post("/chat/editLead", payload)

    async def chat_find(self, filters: dict[str, Any]) -> dict:
        return await self._post("/chat/find", filters)

    async def get_profile(
        self,
        number: str,
        *,
        preview: bool = True,
        return_more_names: bool = False,
    ) -> dict:
        return await self._post("/chat/GetNameAndImageURL", {
            "number": number,
            "preview": preview,
            "returnMoreNames": return_more_names,
        })

    async def check_number(self, numbers: list[str]) -> dict:
        return await self._post("/chat/check", {"numbers": numbers})

    async def block(self, number: str, block: bool = True) -> dict:
        return await self._post("/chat/block", {"number": number, "block": block})

    # ── Configuração da instância (handoff) ──────────────────

    async def update_chatbot_settings(
        self,
        *,
        chatbot_enabled: bool = True,
        chatbot_ignore_groups: bool = True,
        chatbot_stop_conversation: str = "",
        chatbot_stop_minutes: int = 0,
        chatbot_stop_when_you_send_msg: int = 30,
    ) -> dict:
        return await self._post("/instance/updatechatbotsettings", {
            "chatbot_enabled": chatbot_enabled,
            "chatbot_ignoreGroups": chatbot_ignore_groups,
            "chatbot_stopConversation": chatbot_stop_conversation,
            "chatbot_stopMinutes": chatbot_stop_minutes,
            "chatbot_stopWhenYouSendMsg": chatbot_stop_when_you_send_msg,
        })

    # ── lifecycle ────────────────────────────────────────────

    async def close(self) -> None:
        await self.client.aclose()
