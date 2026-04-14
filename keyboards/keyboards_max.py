"""Inline-клавиатуры в формате MAX API (список рядов callback-кнопок)."""

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
    buttons: list[dict] = []
    if not work_is_started and not work_is_ended and not is_vocation and not dinner_started:
        buttons.append(_callback("Приступить к работе", "work_start"))
        buttons.append(_callback("Не работаю", "vocation_start"))
    if work_is_started and not work_is_ended and not dinner_started:
        buttons.append(_callback("Закончить смену", "work_end"))
    if work_is_started and not dinner_started:
        buttons.append(_callback("Перерыв", "dinner_start"))
    elif work_is_started and dinner_started:
        buttons.append(_callback("Закончить перерыв", "dinner_end"))
        buttons.append(_callback("Перерыв уже окончен", "dinner_end_input"))
    if is_vocation:
        buttons.append(_callback("Выйти на работу", "vocation_end"))
    return _layout_rows(buttons, width)


def evening_menu_max() -> list[list[dict]]:
    return [
        [_callback("Закончить смену", "work_end")],
        [_callback("Еще 15 минут", "work_delay_15")],
        [_callback("Еще час", "work_delay_60")],
    ]
