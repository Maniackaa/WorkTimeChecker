"""Inline-клавиатуры MAX — те же сценарии и payload, что у keyboards.py (Telegram)."""

import datetime

import logging

log = logging.getLogger(__name__)


def _callback(text: str, payload: str) -> dict:
    return {"type": "callback", "text": text, "payload": payload}


def _layout_rows(flat_buttons: list[dict], width: int) -> list[list[dict]]:
    rows: list[list[dict]] = []
    for i in range(0, len(flat_buttons), width):
        rows.append(flat_buttons[i : i + width])
    return rows


def custom_kb_max(width: int, buttons_dict: dict[str, str]) -> list[list[dict]]:
    flat = [_callback(k, v) for k, v in buttons_dict.items()]
    return _layout_rows(flat, width)


def get_dinner_menu_max(width: int = 1) -> list[list[dict]]:
    buttons = [
        _callback("✅ Закончить перерыв", "dinner_end"),
        _callback("⌚️ Ввести время окончания перерыва ", "dinner_end_input"),
    ]
    return _layout_rows(buttons, width)


def get_after_start_menu_max(width: int = 1) -> list[list[dict]]:
    buttons = [
        _callback("✅ Перерыв", "dinner_start"),
        _callback("❌ Закончить смену?", "work_end_question"),
    ]
    return _layout_rows(buttons, width)


def get_confirm_end_menu_max(width: int = 1) -> list[list[dict]]:
    buttons = [
        _callback("❌ Закончить смену", "confirm_work_end"),
        _callback("✅ Работать дальше ", "work_continue"),
    ]
    return _layout_rows(buttons, width)


def get_menu_max(
    width: int,
    work_is_started: bool = False,
    work_is_ended: bool = False,
    is_vocation: bool = False,
    dinner_started: bool = False,
) -> list[list[dict]] | None:
    log.info(
        "MAX menu: started=%s ended=%s vocation=%s dinner=%s",
        work_is_started,
        work_is_ended,
        is_vocation,
        dinner_started,
    )
    if work_is_started and work_is_ended:
        return None
    now = datetime.datetime.now()
    buttons: list[dict] = []

    if work_is_started and not dinner_started:
        buttons.append(_callback("✅ Перерыв", "dinner_start"))

    if not work_is_started and not work_is_ended and not is_vocation and not dinner_started:
        buttons.append(_callback("Приступить к работе", "work_start"))
        buttons.append(_callback("Не работаю", "vocation_start"))

    if work_is_started and not work_is_ended and not dinner_started:
        if now.hour >= 17:
            buttons.append(_callback("⏱️ Закончу через 15 минут", "work_delay_15"))
            buttons.append(_callback("⏰ Закончу через 30 минут", "work_delay_30"))
            buttons.append(_callback("🕰  Закончу через час", "work_delay_60"))
        buttons.append(_callback("⌚️ Ввести время окончания смены", "work_end_manual"))
        buttons.append(_callback("❌ Закончить смену?", "work_end_question"))

    elif work_is_started and dinner_started:
        buttons.append(_callback("✅ Закончить перерыв", "dinner_end"))
        buttons.append(_callback("⌚️ Ввести время окончания перерыва ", "dinner_end_input"))

    if is_vocation:
        buttons.append(_callback("Выйти на работу", "vocation_end"))

    return _layout_rows(buttons, width)
