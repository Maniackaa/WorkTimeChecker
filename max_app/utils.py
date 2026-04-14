"""Разбор событий MAX (chat_id, тип чата) для обработчиков."""


def get_chat_id_from_event(event) -> int | None:
    chat_id = None
    if hasattr(event, "message") and event.message:
        msg = event.message
        if hasattr(msg, "recipient") and msg.recipient:
            chat_id = getattr(msg.recipient, "chat_id", None)
        if not chat_id and hasattr(msg, "chat_id"):
            chat_id = msg.chat_id
    if (not chat_id or chat_id == 0) and hasattr(event, "callback") and hasattr(event.callback, "user"):
        chat_id = getattr(event.callback.user, "user_id", None)
    return chat_id


def get_chat_type_label(event) -> str:
    """Человекочитаемый тип чата, если поля есть в API."""
    if not hasattr(event, "message") or not event.message:
        return "неизвестно"
    msg = event.message
    recipient = getattr(msg, "recipient", None)
    if not recipient:
        return "неизвестно"
    for attr in ("chat_type", "type", "recipient_type"):
        val = getattr(recipient, attr, None)
        if val is not None:
            return str(val)
    return "диалог или группа (тип не передан клиентом)"


def get_message_id_from_event(event) -> str | None:
    message_id = None
    if hasattr(event, "message") and event.message:
        msg = event.message
        if hasattr(msg, "body") and msg.body:
            message_id = getattr(msg.body, "mid", None)
    if not message_id and hasattr(event, "callback") and hasattr(event.callback, "message"):
        cm = event.callback.message
        if hasattr(cm, "body") and cm.body:
            message_id = getattr(cm.body, "mid", None)
    return message_id


def is_private_work_chat(event) -> bool:
    """Учёт времени — не в группе (если тип чата приходит в событии)."""
    if not hasattr(event, "message") or not event.message:
        return True
    recipient = getattr(event.message, "recipient", None)
    if recipient:
        ct = getattr(recipient, "chat_type", None) or getattr(recipient, "type", None)
        if ct is not None and str(ct).lower() in ("group", "channel", "supergroup"):
            return False
    return True


def get_configured_group_hint() -> str:
    from config.max_settings import max_settings

    gid = max_settings.MAX_GROUP_CHAT_ID
    if gid:
        return f"MAX_GROUP_CHAT_ID из .env: {gid}"
    return "MAX_GROUP_CHAT_ID в .env не задан — укажите chat_id группы после проверки командой /id в этой группе."
