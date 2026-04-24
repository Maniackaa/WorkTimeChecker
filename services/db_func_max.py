import asyncio
import datetime
import logging

import aiohttp
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import joinedload

from config.max_settings import max_settings
from database.db_max import SessionMax, UserMax, WorkMax
from keyboards.keyboards_max import get_menu_max
from max_app.messaging import delete_message, mid_from_response, send_message

log = logging.getLogger(__name__)


async def _broadcast_summary_text_max(session: aiohttp.ClientSession, text: str) -> None:
    """Сводка в группы (chat_id) и копии в ЛС указанным user_id — разные параметры MAX API."""
    gids = max_settings.get_group_chat_ids_for_broadcast()
    uids = max_settings.get_summary_broadcast_user_ids()
    if not gids and not uids:
        log.warning(
            "MAX сводка: не отправлена — пусто MAX_GROUP_CHAT_ID и MAX_BROADCAST_USER_IDS "
            "(настройте chat_id групп в .env)"
        )
        return
    for cid in gids:
        log.info("MAX: отправка сводки в группу chat_id=%s text_len=%s", cid, len(text))
        res = await send_message(session, chat_id=cid, text=text)
        if res is None:
            log.warning("MAX: сводка в chat_id=%s — API не вернул успешный ответ (см. max_app.messaging)", cid)
        else:
            log.info(
                "MAX: сводка в группу chat_id=%s отправлена mid=%s",
                cid,
                mid_from_response(res),
            )
        await asyncio.sleep(0.05)
    for uid in uids:
        log.info("MAX: отправка копии сводки в ЛС user_id=%s text_len=%s", uid, len(text))
        res = await send_message(session, user_id=uid, text=text)
        if res is None:
            log.warning("MAX: сводка user_id=%s — API не вернул успешный ответ", uid)
        else:
            log.info("MAX: сводка в ЛС user_id=%s отправлена mid=%s", uid, mid_from_response(res))
        await asyncio.sleep(0.05)


def check_user_max(max_uid: str) -> UserMax | None:
    with SessionMax() as session:
        return session.query(UserMax).filter(UserMax.max_user_id == str(max_uid)).one_or_none()


def get_user_max_from_pk(pk: int) -> UserMax | None:
    with SessionMax(expire_on_commit=False) as session:
        return session.execute(select(UserMax).filter(UserMax.id == pk)).scalars().one_or_none()


def get_or_create_user_max(sender) -> UserMax | None:
    try:
        max_uid = str(sender.user_id)
        username = getattr(sender, "username", None)
        full_name = (
            f"{getattr(sender, 'first_name', None) or ''} {getattr(sender, 'last_name', None) or ''}".strip()
        )
        session = SessionMax(expire_on_commit=False)
        with session:
            old = check_user_max(max_uid)
            if old:
                if not old.username and username:
                    old.username = username
                if not old.fio and full_name:
                    old.fio = full_name
                session.add(old)
                session.commit()
                return old
            new_user = UserMax(
                max_user_id=max_uid,
                username=username,
                register_date=datetime.datetime.now(),
                fio=full_name or None,
            )
            session.add(new_user)
            session.commit()
            log.debug("Создан пользователь MAX: %s", new_user)
            return new_user
    except Exception:
        log.exception("Пользователь MAX не создан")
        return None


def start_work_max(user_id: int, date, start_time) -> None:
    log.info("start_work_max user_id=%s date=%s start=%s", user_id, date, start_time)
    session = SessionMax(expire_on_commit=False)
    with session:
        q = select(WorkMax).where(WorkMax.user_id == user_id).where(WorkMax.date == date)
        work = session.execute(q).scalars().one_or_none()
        day = date if isinstance(date, datetime.date) else datetime.date.today()
        if not work:
            work = WorkMax(user_id=user_id, date=day, begin=start_time)
            session.add(work)
        else:
            work.begin = start_time
        session.commit()


async def end_work_max(user: UserMax, date, end_time, session: aiohttp.ClientSession) -> None:
    log.info("end_work_max user=%s date=%s end=%s", user, date, end_time)
    s = SessionMax(expire_on_commit=False)
    with s:
        q = select(WorkMax).where(WorkMax.user_id == user.id).where(WorkMax.date == date)
        work = s.execute(q).scalars().one_or_none()
        day = date if isinstance(date, datetime.date) else datetime.date.today()
        if not work:
            work = WorkMax(user_id=user.id, date=day, end=end_time)
            s.add(work)
        else:
            work.end = end_time
        s.commit()

    work = get_today_work_max(user.id)
    text = format_message_max(user, work)
    await _broadcast_summary_text_max(session, text)
    await send_message(session, user_id=int(user.max_user_id), text=f"Смена окончена: {end_time}")


def get_today_work_max(user_id: int) -> WorkMax:
    session = SessionMax(expire_on_commit=False)
    today = datetime.date.today()
    with session:
        q = select(WorkMax).where(WorkMax.user_id == user_id).where(WorkMax.date == today)
        work = session.execute(q).scalars().one_or_none()
    if not work:
        work = WorkMax(user_id=user_id, date=today)
    return work


def morning_users_max() -> list[UserMax]:
    """Как morning_users() в services/db_func.py: outerjoin смены за сегодня и проверка user.works[-1]."""
    try:
        session = SessionMax(expire_on_commit=False)
        today = datetime.date.today()
        with session:
            stmt = (
                select(UserMax)
                .where(
                    and_(
                        UserMax.is_worked == 1,
                        or_(UserMax.vacation_to.is_(None), UserMax.vacation_to <= today),
                    )
                )
                .outerjoin(WorkMax, and_(WorkMax.user_id == UserMax.id, WorkMax.date == today))
                .options(joinedload(UserMax.works))
            )
            users = list(session.scalars(stmt).unique().all())
        available_users: list[UserMax] = []
        for user in users:
            if not user.works:
                available_users.append(user)
            else:
                last_work = user.works[-1]
                if last_work.date != today or (last_work.date == today and not last_work.begin):
                    available_users.append(user)
        log.debug("MAX morning users: %s", available_users)
        return available_users
    except Exception as e:
        log.error("morning_users_max: %s", e, exc_info=True)
        return []


def evening_users_max() -> list[UserMax]:
    session = SessionMax(expire_on_commit=False)
    today = datetime.date.today()
    with session:
        query = (
            session.query(UserMax)
            .join(WorkMax, UserMax.id == WorkMax.user_id, isouter=True)
            .filter(WorkMax.begin.is_not(None))
            .filter(WorkMax.end.is_(None))
            .filter(WorkMax.date == today)
            .options(joinedload(UserMax.works))
        )
        users = query.all()
    log.debug("MAX evening users: %s", users)
    return users


def all_evening_users_max() -> list[UserMax]:
    """То же множество, что evening_users_max (как all_evening_users в TG)."""
    return evening_users_max()


def vocation_users_max() -> list[UserMax]:
    session = SessionMax(expire_on_commit=False)
    today = datetime.date.today()
    with session:
        users = session.query(UserMax).filter(UserMax.vacation_to > today).all()
    log.info("MAX в отпуске: %s", users)
    return users


def check_work_is_started_max(user_id: int) -> bool:
    session = SessionMax(expire_on_commit=False)
    today = datetime.date.today()
    with session:
        work = session.query(WorkMax).filter(WorkMax.user_id == user_id).filter(WorkMax.date == today).one_or_none()
    if not work or not work.begin:
        return False
    return True


def check_work_is_ended_max(user_id: int) -> bool:
    session = SessionMax(expire_on_commit=False)
    today = datetime.date.today()
    with session:
        work = session.query(WorkMax).filter(WorkMax.user_id == user_id).filter(WorkMax.date == today).one_or_none()
    return bool(work and work.end)


def check_is_vocation_max(user_id: int) -> bool:
    session = SessionMax(expire_on_commit=False)
    today = datetime.date.today()
    with session:
        user = session.query(UserMax).filter(UserMax.id == user_id).one_or_none()
    if not user:
        return False
    return bool(user.vacation_to and user.vacation_to > today)


def check_dinner_start_max(user_id: int) -> bool:
    session = SessionMax(expire_on_commit=False)
    today = datetime.date.today()
    with session:
        work = session.query(WorkMax).filter(WorkMax.user_id == user_id).filter(WorkMax.date == today).one_or_none()
    if work:
        return bool(work.dinner_start and not work.dinner_end)
    return False


async def delete_msg_max(session: aiohttp.ClientSession, message_id: str | None) -> None:
    if not message_id:
        return
    try:
        await delete_message(session, str(message_id))
    except Exception as e:
        log.warning("delete_msg_max: %s", e)


async def evening_send_max(session: aiohttp.ClientSession) -> None:
    log.info("MAX вечерняя рассылка")
    users_to_send = evening_users_max()
    log.info("MAX вечер: к отправке %s чел.", len(users_to_send))
    text = "Рабочий день окончен"
    for user in users_to_send:
        try:
            work = get_today_work_max(user.id)
            work_is_started = check_work_is_started_max(user.id)
            work_is_ended = check_work_is_ended_max(user.id)
            is_vocation = check_is_vocation_max(user.id)
            dinner_start = check_dinner_start_max(user.id)
            await delete_msg_max(session, user.last_message)
            now_ep = datetime.datetime.now().replace(microsecond=0)
            if dinner_start:
                log.info("%s на перерыве", user)
                menu = get_menu_max(1, work_is_started, work_is_ended, is_vocation, dinner_started=dinner_start)
                res = await send_message(
                    session,
                    user_id=int(user.max_user_id),
                    text="Рабочий день окончен? Закончите перерыв!",
                    buttons=menu,
                )
                mid = mid_from_response(res)
                if mid:
                    user.set("last_message", mid)
                    work.set("evening_prompt_at", now_ep)
                await asyncio.sleep(0.1)
                continue
            menu = get_menu_max(1, work_is_started, work_is_ended, is_vocation, dinner_started=dinner_start)
            res = await send_message(session, user_id=int(user.max_user_id), text=text, buttons=menu)
            mid = mid_from_response(res)
            if mid:
                user.set("last_message", mid)
                work.set("evening_prompt_at", now_ep)
            log.info("Вечернее сообщение отправлено: %s", user)
            await asyncio.sleep(0.1)
        except Exception as err:
            log.error("Ошибка вечерней отправки %s: %s", user, err, exc_info=False)


def format_message_max(user: UserMax, work: WorkMax) -> str:
    work_durations = calculate_work_durations_max(user.id)
    uname = f"@{user.username}" if user.username else "—"
    begin_t = work.begin.time() if work.begin else "—"
    end_t = work.end.time() if work.end else "—"
    return (
        f"{user.fio}\n"
        f"Username: {uname}\n"
        f"Дата: {work.date.strftime('%d.%m.%Y')}\n"
        f"Начало: {begin_t}\n"
        f"Окончание: {end_t}\n"
        f"Перерывы: {work.total_dinner // 60} мин.\n"
        f"Продолжительность:\n"
        f"Сегодня: {work_durations['today']}\n"
        f"Неделя: {work_durations['week']}\n"
        f"Месяц: {work_durations['month']}\n"
    )


def format_total_time(total_seconds: float) -> str:
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    return f"{hours} часов {minutes} минут"


def calculate_work_durations_max(user_id: int) -> dict[str, str]:
    today = datetime.date.today()
    now = datetime.datetime.now()
    start_of_week = today - datetime.timedelta(days=today.weekday())
    start_of_month = today.replace(day=1)

    def calculate_total_seconds(work_list: list[WorkMax]) -> str:
        total_seconds = 0.0
        for w in work_list:
            if w.begin and w.end:
                total_seconds += (w.end - w.begin).total_seconds()
            elif w.begin and not w.end:
                total_seconds += (now - w.begin).total_seconds()
            if w.total_dinner:
                total_seconds -= w.total_dinner
        return format_total_time(total_seconds)

    session = SessionMax(expire_on_commit=False)
    with session:
        stmt_today = select(WorkMax).where(WorkMax.user_id == user_id, WorkMax.date == today)
        works_today = session.scalars(stmt_today).all()

        stmt_week = select(WorkMax).where(
            WorkMax.user_id == user_id, WorkMax.date >= start_of_week, WorkMax.date <= today
        )
        works_week = session.scalars(stmt_week).all()

        stmt_month = select(WorkMax).where(
            WorkMax.user_id == user_id, WorkMax.date >= start_of_month, WorkMax.date <= today
        )
        works_month = session.scalars(stmt_month).all()

    return {
        "today": calculate_total_seconds(list(works_today)),
        "week": calculate_total_seconds(list(works_week)),
        "month": calculate_total_seconds(list(works_month)),
    }


async def morning_send_max(session: aiohttp.ClientSession) -> None:
    try:
        users_to_send = morning_users_max()
        log.info("MAX утро: к отправке %s чел.", len(users_to_send))
        text = "Вы на рабочем месте?  Начинаем работу?"
        menu = get_menu_max(1, work_is_started=False, work_is_ended=False)
        for user in users_to_send:
            try:
                await delete_msg_max(session, user.last_message)
                res = await send_message(session, user_id=int(user.max_user_id), text=text, buttons=menu)
                mid = mid_from_response(res)
                if mid:
                    user.set("last_message", mid)
                log.info("Утреннее сообщение MAX: %s", user)
                await asyncio.sleep(0.1)
            except Exception as err:
                log.error("Ошибка утренней отправки %s: %s", user, err, exc_info=False)
    except Exception as err:
        log.error("morning_send_max: %s", err, exc_info=True)


async def end_task_max(session: aiohttp.ClientSession, scheduler=None) -> None:
    """Завершение дня — та же двухфазная логика, что `end_task` в main.py (Telegram)."""
    del scheduler  # оставлен в сигнатуре для совместимости с планировщиком
    log.info("MAX завершение дня")
    today = datetime.date.today()
    users_with_empty_work_end_today = evening_users_max()
    log.info("MAX на смене: %s", users_with_empty_work_end_today)
    for user in users_with_empty_work_end_today:
        log.info("%s не закончил смену", user)
        work = get_today_work_max(user.id)
        if not work.last_reaction:
            if check_dinner_start_max(user.id) and work.dinner_start:
                log.info("%s: на перерыве, реакции нет — закрываем по времени ухода на перерыв", user)
                await end_work_max(user, today, work.dinner_start, session)
                work.set("dinner_start", None)
                await delete_msg_max(session, user.last_message)
            elif work.evening_prompt_at:
                log.info("%s: реакции не было после вечернего — условное окончание в 17.00", user)
                end_time1 = datetime.datetime.combine(today, datetime.time(17, 0))
                end_time2 = work.begin
                end_time = max(end_time1, end_time2) if work.begin else end_time1
                await end_work_max(user, today, end_time, session)
                await delete_msg_max(session, user.last_message)
            else:
                log.info("%s: вечернее не отмечено как отправленное — закрытие по фактическому времени", user)
                await end_work_max(user, today, datetime.datetime.now().replace(microsecond=0), session)
                await delete_msg_max(session, user.last_message)
        else:
            log.info("%s есть реакция в %s", user, work.last_reaction)

    users = all_evening_users_max()
    log.info("MAX осталось на смене: %s", users)
    if users:
        log.info("Хватит работать!")
        for user in users:
            log.info("%s еще на смене", user)
            work = get_today_work_max(user.id)
            if work.dinner_start and not work.dinner_end:
                log.info("%s на обеде", user)
                await end_work_max(user, today, work.dinner_start, session)
                work.set("dinner_start", None)
                continue
            if work.last_reaction:
                log.info("%s есть реакция %s", user, work.last_reaction)
                endtime = work.last_reaction
            else:
                log.info("%s нет реакции", user)
                endtime = datetime.datetime.combine(today, datetime.time(17, 0))
            await end_work_max(user, today, endtime, session)


async def _send_max_interval_digest_to_admins(
    session: aiohttp.ClientSession,
    *,
    n_morning: int,
    n_evening_before: int,
    n_evening_after: int,
    n_vacation: int,
) -> None:
    """В тестовом режиме по интервалу — одно сообщение админам со сводкой (почему личные рассылки могут быть 0)."""
    interval = max_settings.MAX_REPORT_INTERVAL_MINUTES
    if not interval or interval <= 0:
        return
    admin_ids, _ = max_settings.get_admin_ids_for_notify()
    if not admin_ids:
        log.info("MAX тест-дайджест: MAX_ADMIN_IDS пуст — некому отправить сводку")
        return
    now = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
    gids = max_settings.get_group_chat_ids_for_broadcast()
    buids = max_settings.get_summary_broadcast_user_ids()
    group_line = (
        f"чатов (chat_id) для сводок: {len(gids)} ({', '.join(map(str, gids)) or '—'})"
        if gids
        else "чаты: нет (MAX_GROUP_CHAT_ID — только id групп/каналов, не user_id)"
    )
    user_line = (
        f"копий в ЛС (user_id): {len(buids)} ({', '.join(map(str, buids))})"
        if buids
        else "ЛС по user_id: нет (MAX_BROADCAST_USER_IDS)"
    )
    text = (
        f"[Тест MAX, каждые {interval} мин] {now}\n\n"
        f"Утро (не начали смену сегодня): {n_morning} чел.\n"
        f"Вечер (смена открыта, без конца): до тика {n_evening_before}, после {n_evening_after} чел.\n"
        f"В отпуске: {n_vacation} чел.\n"
        f"{group_line}\n"
        f"{user_line}\n\n"
        "Личные напоминания не приходят, если вы уже закрыли смену за сегодня "
        "(есть и начало, и конец). Тогда списки «утро» и «вечер» для вас пустые — это норма.\n"
        "Утро — только у кого is_worked и сегодня ещё нет begin. "
        "Вечер — у кого есть begin сегодня, но нет end."
    )
    for aid in admin_ids:
        try:
            await send_message(session, user_id=aid, text=text)
        except Exception as e:
            log.warning("MAX тест-дайджест админу %s: %s", aid, e)


async def run_all_max_scheduled_reports(session: aiohttp.ClientSession, scheduler) -> None:
    """Один тик всех плановых рассылок (для теста по интервалу)."""
    test_mode = bool(max_settings.MAX_REPORT_INTERVAL_MINUTES and max_settings.MAX_REPORT_INTERVAL_MINUTES > 0)
    n_mor = len(morning_users_max()) if test_mode else 0
    n_eve_b = len(evening_users_max()) if test_mode else 0
    n_vac = len(vocation_users_max()) if test_mode else 0

    await morning_send_max(session)
    await evening_send_max(session)
    await end_task_max(session, scheduler)
    await vocation_task_max(session)

    if test_mode:
        n_eve_a = len(evening_users_max())
        await _send_max_interval_digest_to_admins(
            session,
            n_morning=n_mor,
            n_evening_before=n_eve_b,
            n_evening_after=n_eve_a,
            n_vacation=n_vac,
        )


async def vocation_task_max(session: aiohttp.ClientSession) -> None:
    users_to_send = vocation_users_max()
    today = datetime.date.today()
    gids = max_settings.get_group_chat_ids_for_broadcast()
    uids = max_settings.get_summary_broadcast_user_ids()
    if not gids and not uids:
        log.warning("Нет получателей сводок по отпускам: задайте MAX_GROUP_CHAT_ID (чаты) и/или MAX_BROADCAST_USER_IDS")
        return
    for user in users_to_send:
        uname = f"@{user.username}" if user.username else "—"
        msg = (
            f"{user.fio}\n"
            f"Username: {uname}\n"
            f"Дата: {today.strftime('%d.%m.%Y')}\n"
            f"Не работает до: {user.vacation_to.strftime('%d.%m.%Y')}\n"
        )
        await _broadcast_summary_text_max(session, msg)
        await asyncio.sleep(0.1)
