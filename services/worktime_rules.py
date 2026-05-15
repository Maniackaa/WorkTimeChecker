"""Общие правила расчёта времени при дозакрытии смены (TG и MAX)."""

from __future__ import annotations

import datetime
from typing import Any


def evening_auto_close_end(today: datetime.date, work: Any) -> datetime.datetime:
    """
    Авто-время конца смены при дозакрытии дня.

    Ожидание по last_reaction: время ухода на перерыв (пока не вернулись) или времени возврата
    после перерыва; также туда может писаться план «закончу через N минут».
    Итог: не раньше max(17:00, начало смены) и не раньше last_reaction, если он задан — поэтому
    перерыв до 13:14 не тянет конец ниже правила 17:00, а возврат в 18:00 поднимает его до 18:00.
    """
    t17 = datetime.datetime.combine(today, datetime.time(17, 0))
    base = max(t17, work.begin) if work.begin else t17
    lr = getattr(work, "last_reaction", None)
    if lr is not None:
        return max(base, lr)
    return base
