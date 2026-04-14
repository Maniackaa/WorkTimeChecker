"""Сырой MAX REST API: отправка текста, клавиатур, удаление сообщений."""

from __future__ import annotations

import json
import logging
from typing import Any

import aiohttp

from config.max_settings import max_settings

log = logging.getLogger(__name__)


def mid_from_response(data: dict[str, Any] | None) -> str | None:
    if not data or "message" not in data:
        return None
    body = data["message"].get("body") or {}
    return body.get("mid")


async def send_message(
    session: aiohttp.ClientSession,
    *,
    user_id: int | None = None,
    chat_id: int | None = None,
    text: str,
    buttons: list | None = None,
) -> dict[str, Any] | None:
    if not session:
        return None
    base = max_settings.api_base_url
    url = f"{base}/messages"
    headers = {
        "Authorization": max_settings.MAX_BOT_TOKEN,
        "Content-Type": "application/json",
    }
    params: dict[str, int] = {}
    if chat_id is not None:
        params["chat_id"] = int(chat_id)
    elif user_id is not None:
        params["user_id"] = int(user_id)
    else:
        log.warning("send_message: нет ни chat_id, ни user_id")
        return None

    attachments: list[dict] = []
    if buttons:
        attachments.append({"type": "inline_keyboard", "payload": {"buttons": buttons}})
    body: dict[str, Any] = {"text": text, "attachments": attachments}

    try:
        log.debug(
            "MAX POST /messages params=%s text_len=%s has_buttons=%s",
            params,
            len(text),
            bool(buttons),
        )
        async with session.post(url, headers=headers, params=params, json=body) as resp:
            body_txt = await resp.text()
            if resp.status == 200:
                if not body_txt:
                    log.debug("MAX POST /messages 200, тело ответа пустое")
                    return None
                try:
                    return json.loads(body_txt)
                except json.JSONDecodeError:
                    log.warning("MAX POST /messages 200, не JSON: %s", body_txt[:500])
                    return None
            log.warning(
                "MAX отправка сообщения: HTTP %s params=%s ответ=%s",
                resp.status,
                params,
                body_txt[:800] if body_txt else "(пусто)",
            )
            return None
    except Exception as e:
        log.warning("Исключение при отправке MAX params=%s: %s", params, e, exc_info=True)
        return None


async def delete_message(session: aiohttp.ClientSession, message_id: str) -> bool:
    if not session or not message_id:
        return False
    base = max_settings.api_base_url
    url = f"{base}/messages"
    headers = {
        "Authorization": max_settings.MAX_BOT_TOKEN,
        "Content-Type": "application/json",
    }
    try:
        async with session.delete(url, headers=headers, params={"message_id": message_id}) as resp:
            if resp.status == 200:
                return True
            if resp.status == 404:
                return False
            err = await resp.text()
            log.warning("Ошибка удаления MAX %s: %s", resp.status, err[:200])
            return False
    except Exception as e:
        log.warning("Исключение при удалении MAX: %s", e)
        return False
