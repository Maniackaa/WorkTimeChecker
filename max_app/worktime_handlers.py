"""Обработчики учёта времени для MAX (аналог handlers/user_handlers.py)."""

from __future__ import annotations

import datetime
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from maxapi import Dispatcher
from maxapi.types import Command, MessageCallback, MessageCreated

from api import format_datetime
from database.db_max import Timer
from keyboards.keyboards_max import (
    custom_kb_max,
    get_after_start_menu_max,
    get_confirm_end_menu_max,
    get_dinner_menu_max,
    get_menu_max,
)
from max_app import context
from max_app.messaging import mid_from_response, send_message
from max_app.utils import (
    get_chat_id_from_event,
    get_chat_type_label,
    get_message_id_from_event,
    is_private_work_chat,
)
from services.db_func_max import (
    _broadcast_summary_text_max,
    check_dinner_start_max,
    check_is_vocation_max,
    check_work_is_ended_max,
    check_work_is_started_max,
    delay_send_max,
    delete_msg_max,
    end_work_max,
    format_message_max,
    get_or_create_user_max,
    get_today_work_max,
    start_work_max,
)

log = logging.getLogger(__name__)

processed_callbacks: set[str] = set()
# FSM: user_id -> "vacation" | "dinner_end" | "work_end"
max_user_fsm: dict[int, str] = {}


def _session():
    return context.http_session


async def _answer_text(event: MessageCreated, text: str) -> None:
    await event.message.answer(text)


async def _send_menu_user(event: MessageCreated, user, text: str, menu) -> None:
    s = _session()
    if not s:
        await _answer_text(event, text)
        return
    uid = int(event.message.sender.user_id)
    res = await send_message(s, user_id=uid, text=text, buttons=menu)
    mid = mid_from_response(res)
    if mid:
        user.set("last_message", mid)


async def _send_menu_callback(event: MessageCallback, user, text: str, menu) -> None:
    s = _session()
    if not s:
        return
    uid = int(event.callback.user.user_id)
    res = await send_message(s, user_id=uid, text=text, buttons=menu)
    mid = mid_from_response(res)
    if mid:
        user.set("last_message", mid)


def register_worktime_handlers(dp: Dispatcher) -> None:
    @dp.message_created(Command("start"))
    async def cmd_start_worktime(event: MessageCreated):
        if not is_private_work_chat(event):
            await _answer_text(event, "Учёт времени доступен в личных сообщениях с ботом.")
            return
        s = _session()
        if not s:
            await _answer_text(event, "Бот ещё инициализируется, попробуйте через секунду.")
            return
        user = get_or_create_user_max(event.message.sender)
        if not user:
            await _answer_text(event, "Не удалось сохранить профиль. Обратитесь к администратору.")
            return
        log.info("MAX старт: %s", user)
        if user.last_message:
            await delete_msg_max(s, user.last_message)
        work_is_started = check_work_is_started_max(user.id)
        work_is_ended = check_work_is_ended_max(user.id)
        is_vocation = check_is_vocation_max(user.id)
        dinner_start = check_dinner_start_max(user.id)
        menu_kb = get_menu_max(1, work_is_started, work_is_ended, is_vocation, dinner_started=dinner_start)
        if work_is_started and work_is_ended:
            await _answer_text(event, "Вы уже сегодня отработали")
        elif work_is_started and not work_is_ended:
            await _send_menu_user(event, user, "Закончить смену?", menu_kb)
        elif is_vocation:
            await _send_menu_user(event, user, f"Вы в отпуске до {user.vacation_to}", menu_kb)
        else:
            await _send_menu_user(event, user, "Вы на рабочем месте?  Начинаем работу?", menu_kb)

    @dp.message_created(Command("id"))
    async def cmd_id(event: MessageCreated):
        user = event.message.sender
        user_id = user.user_id
        chat_id = get_chat_id_from_event(event)
        first = getattr(user, "first_name", None) or ""
        last = getattr(user, "last_name", None) or ""
        name = f"{first} {last}".strip() or "—"
        username = getattr(user, "username", None) or "—"
        chat_type = get_chat_type_label(event)
        text = (
            "Идентификаторы MAX\n\n"
            f"user_id: {user_id}\n"
            f"Имя: {name}\n"
            f"Username: {username}\n\n"
            f"chat_id: {chat_id}\n"
            f"Тип чата: {chat_type}"
        )
        await event.message.answer(text)

    @dp.message_callback()
    async def on_callback(event: MessageCallback):
        cb_id = getattr(event.callback, "callback_id", None)
        if cb_id and cb_id in processed_callbacks:
            return
        if cb_id:
            processed_callbacks.add(cb_id)
            if len(processed_callbacks) > 1000:
                processed_callbacks.clear()

        payload = getattr(event.callback, "payload", None)
        if not payload:
            return
        s = _session()
        if not s:
            return

        mid = get_message_id_from_event(event)
        if mid:
            await delete_msg_max(s, mid)

        user = get_or_create_user_max(event.callback.user)
        if not user:
            return

        if payload == "work_start":
            log.info("MAX work_start %s", user)
            today = datetime.date.today()
            now = datetime.datetime.now().replace(microsecond=0)
            work_is_started = check_work_is_started_max(user.id)
            work_is_ended = check_work_is_ended_max(user.id)
            is_vocation = check_is_vocation_max(user.id)
            dinner_start = check_dinner_start_max(user.id)
            menu_kb = get_menu_max(1, work_is_started, work_is_ended, is_vocation, dinner_started=dinner_start)
            if work_is_started and not work_is_ended:
                tw = get_today_work_max(user.id)
                await _send_menu_callback(event, user, f"Вы уже начали смену в {tw.begin}", menu_kb)
                return
            if work_is_started and work_is_ended:
                await send_message(s, user_id=int(user.max_user_id), text="Вы уже сегодня отработали")
                return
            start_work_max(user.id, today, now)
            after_menu = get_after_start_menu_max(1)
            await send_message(s, user_id=int(user.max_user_id), text=f"Смена начата: {now}")
            res = await send_message(s, user_id=int(user.max_user_id), text="Выберете действие:", buttons=after_menu)
            mid_new = mid_from_response(res)
            if mid_new:
                user.set("last_message", mid_new)

        elif payload == "work_end_question":
            menu = get_confirm_end_menu_max(1)
            await send_message(s, user_id=int(user.max_user_id), text="Завершить смену?", buttons=menu)

        elif payload == "work_continue":
            log.info("MAX work_continue %s", user)
            work_is_started = check_work_is_started_max(user.id)
            work_is_ended = check_work_is_ended_max(user.id)
            is_vocation = check_is_vocation_max(user.id)
            dinner_start = check_dinner_start_max(user.id)
            menu_kb = get_menu_max(1, work_is_started, work_is_ended, is_vocation, dinner_started=dinner_start)
            await send_message(s, user_id=int(user.max_user_id), text="Закончить смену?", buttons=menu_kb)

        elif payload in ("confirm_work_end", "work_end"):
            log.info("MAX confirm_work_end %s", user)
            work = get_today_work_max(user.id)
            work_is_started = check_work_is_started_max(user.id)
            work_is_ended = check_work_is_ended_max(user.id)
            is_vocation = check_is_vocation_max(user.id)
            dinner_start = check_dinner_start_max(user.id)
            menu_kb = get_menu_max(1, work_is_started, work_is_ended, is_vocation, dinner_started=dinner_start)
            if work_is_ended:
                await _send_menu_callback(event, user, f"Вы уже закончили смену в {work.end}", menu_kb)
                return
            if not work_is_started:
                await send_message(s, user_id=int(user.max_user_id), text="Вы не начали смену")
                return
            today = datetime.date.today()
            now = datetime.datetime.now().replace(microsecond=0)
            await end_work_max(user, today, now, s)

        elif payload.startswith("work_delay_"):
            delay = int(payload.split("work_delay_")[1])
            log.info("MAX work_delay %s мин. %s", delay, user)
            work = get_today_work_max(user.id)
            work_is_started = check_work_is_started_max(user.id)
            work_is_ended = check_work_is_ended_max(user.id)
            is_vocation = check_is_vocation_max(user.id)
            dinner_start = check_dinner_start_max(user.id)
            menu_kb = get_menu_max(1, work_is_started, work_is_ended, is_vocation, dinner_started=dinner_start)
            if work_is_ended:
                await send_message(s, user_id=int(user.max_user_id), text=f"Смена окончена: {work.end}")
                return
            if user.last_message:
                with Timer("delete_msg_max"):
                    await delete_msg_max(s, user.last_message)
            target_time = datetime.datetime.now()
            target_time_str = format_datetime(target_time)
            res = await send_message(
                s,
                user_id=int(user.max_user_id),
                text=f"Планируемое врямя окончания: {target_time_str}",
                buttons=menu_kb,
            )
            mid_new = mid_from_response(res)
            if mid_new:
                user.set("last_message", mid_new)
            work.set("last_reaction", target_time)
            run_time = datetime.datetime.now() + datetime.timedelta(minutes=delay)
            sched = AsyncIOScheduler()

            async def _run_delay():
                s2 = context.http_session
                if s2:
                    await delay_send_max(user.id, s2)

            sched.add_job(_run_delay, DateTrigger(run_date=run_time))
            sched.start()
            log.info("MAX delay_send для %s в %s", user, run_time)

        elif payload == "work_end_manual":
            await send_message(
                s,
                user_id=int(user.max_user_id),
                text="Введите время окончания работы: ЧЧ:ММ",
            )
            max_user_fsm[event.callback.user.user_id] = "work_end"

        elif payload == "vocation_start":
            await send_message(
                s,
                user_id=int(user.max_user_id),
                text="Введите дату (дд.мм.гггг) когда планируете вернуться к работе",
            )
            max_user_fsm[event.callback.user.user_id] = "vacation"

        elif payload == "vocation_end":
            user.set("vacation_to", None)
            await send_message(s, user_id=int(user.max_user_id), text="Вы вышли на работу")

        elif payload == "dinner_start":
            work = get_today_work_max(user.id)
            if not work.dinner_start:
                now = datetime.datetime.now().replace(microsecond=0)
                work.set("dinner_start", now)
                work.set("last_reaction", now)
                dinner_menu = get_dinner_menu_max(1)
                await send_message(s, user_id=int(user.max_user_id), text=f"Перерыв начат: {now}")
                res = await send_message(s, user_id=int(user.max_user_id), text="Закончите перерыв", buttons=dinner_menu)
                mid_new = mid_from_response(res)
                if mid_new:
                    user.set("last_message", mid_new)
            else:
                await send_message(
                    s, user_id=int(user.max_user_id), text=f"Перерыв уже начат в {work.dinner_start}"
                )

        elif payload == "dinner_end":
            work = get_today_work_max(user.id)
            now = datetime.datetime.now().replace(microsecond=0)
            if work.dinner_start and not work.dinner_end:
                dinner_time = (now - work.dinner_start).total_seconds()
                work.set("total_dinner", work.total_dinner + dinner_time)
                work.set("dinner_start", None)
                work.set("dinner_end", None)
                work.set("last_reaction", None)
                work_is_started = check_work_is_started_max(user.id)
                work_is_ended = check_work_is_ended_max(user.id)
                is_vocation = check_is_vocation_max(user.id)
                dinner_start = check_dinner_start_max(user.id)
                menu = get_menu_max(1, work_is_started, work_is_ended, is_vocation, dinner_started=dinner_start)
                await send_message(s, user_id=int(user.max_user_id), text=f"Перерыв окончен: {now}")
                res = await send_message(s, user_id=int(user.max_user_id), text="Перерыв окончен", buttons=menu)
                mid_new = mid_from_response(res)
                if mid_new:
                    user.set("last_message", mid_new)

        elif payload == "dinner_end_input":
            await send_message(
                s,
                user_id=int(user.max_user_id),
                text="Введите время окончания перерыва: ЧЧ:ММ",
            )
            max_user_fsm[event.callback.user.user_id] = "dinner_end"

    @dp.message_created()
    async def on_plain_message(event: MessageCreated):
        if not event.message.body or not event.message.body.text:
            return
        text_raw = event.message.body.text.strip()
        if text_raw.startswith("/"):
            return
        if not is_private_work_chat(event):
            return
        uid = event.message.sender.user_id
        state = max_user_fsm.get(uid)
        if not state:
            return
        s = _session()
        if not s:
            return

        if state == "work_end":
            try:
                user = get_or_create_user_max(event.message.sender)
                if not user:
                    max_user_fsm.pop(uid, None)
                    return
                work = get_today_work_max(user.id)
                if work.begin and not work.end:
                    today = datetime.date.today()
                    time_obj = datetime.datetime.strptime(text_raw, "%H:%M").time()
                    work_end_dt = datetime.datetime.combine(today, time_obj)
                    if work_end_dt > datetime.datetime.now():
                        await send_message(s, user_id=uid, text="Время окончания не может быть позже чем сейчас")
                        max_user_fsm.pop(uid, None)
                        return
                    await send_message(s, user_id=uid, text=f"Смена окончена: {format_datetime(work_end_dt)}")
                    work.set("end", work_end_dt)
                    work_ref = get_today_work_max(user.id)
                    text_out = format_message_max(user, work_ref)
                    await _broadcast_summary_text_max(s, text_out)
                max_user_fsm.pop(uid, None)
            except ValueError:
                await send_message(s, user_id=uid, text="Введите время в формате ЧЧ:ММ")
                max_user_fsm.pop(uid, None)

        elif state == "vacation":
            try:
                date_obj = datetime.datetime.strptime(text_raw, "%d.%m.%Y").date()
                user = get_or_create_user_max(event.message.sender)
                if user:
                    user.set("vacation_to", date_obj)
                    kb = custom_kb_max(1, {"Выйти на работу": "vocation_end"})
                    res = await send_message(
                        s,
                        user_id=int(user.max_user_id),
                        text=f"Выход на работу: {date_obj.strftime('%d.%m.%Y')}",
                        buttons=kb,
                    )
                    mid = mid_from_response(res)
                    if mid:
                        user.set("last_message", mid)
            except ValueError:
                log.warning("Неверная дата отпуска: %s", text_raw)
                await send_message(s, user_id=uid, text="Введите дату в формате дд.мм.гггг")
            finally:
                max_user_fsm.pop(uid, None)

        elif state == "dinner_end":
            try:
                user = get_or_create_user_max(event.message.sender)
                if not user:
                    max_user_fsm.pop(uid, None)
                    return
                work = get_today_work_max(user.id)
                if not (work.dinner_start and not work.dinner_end):
                    max_user_fsm.pop(uid, None)
                    return
                today = datetime.date.today()
                time_obj = datetime.datetime.strptime(text_raw, "%H:%M").time()
                dinner_end_dt = datetime.datetime.combine(today, time_obj)
                if dinner_end_dt < work.dinner_start:
                    await send_message(s, user_id=uid, text="Время окончания не может быть ранее начала")
                    return
                dinner_time = (dinner_end_dt - work.dinner_start).total_seconds()
                work.set("total_dinner", work.total_dinner + dinner_time)
                work.set("dinner_start", None)
                work.set("dinner_end", None)
                work.set("last_reaction", None)
                work_is_started = check_work_is_started_max(user.id)
                work_is_ended = check_work_is_ended_max(user.id)
                is_vocation = check_is_vocation_max(user.id)
                dinner_start = check_dinner_start_max(user.id)
                menu = get_menu_max(1, work_is_started, work_is_ended, is_vocation, dinner_started=dinner_start)
                await send_message(s, user_id=uid, text=f"Перерыв окончен: {dinner_end_dt}")
                res = await send_message(s, user_id=uid, text="Закончить смену?", buttons=menu)
                mid = mid_from_response(res)
                if mid:
                    user.set("last_message", mid)
                max_user_fsm.pop(uid, None)
            except ValueError:
                await send_message(s, user_id=uid, text="Ведите время в формате ЧЧ:ММ")
                max_user_fsm.pop(uid, None)
