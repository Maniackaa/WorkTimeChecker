import asyncio
import datetime
import logging

import aiohttp
from apscheduler.triggers.date import DateTrigger
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import joinedload

from config.max_settings import max_settings
from database.db_max import SessionMax, UserMax, WorkMax
from keyboards.keyboards_max import evening_menu_max, get_menu_max
from max_app.messaging import delete_message, mid_from_response, send_message

log = logging.getLogger(__name__)


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
        today = datetime.datetime.today().date()
        if not work:
            work = WorkMax(user_id=user_id, date=today, begin=start_time)
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
        today = datetime.datetime.today().date()
        if not work:
            work = WorkMax(user_id=user.id, date=today, end=end_time)
            s.add(work)
        else:
            work.end = end_time
        s.commit()

    work = get_today_work_max(user.id)
    text = format_message_max(user, work)
    gid = max_settings.MAX_GROUP_CHAT_ID
    if gid:
        await send_message(session, chat_id=int(gid), text=text)
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
    session = SessionMax(expire_on_commit=False)
    today = datetime.date.today()
    with session:
        stmt = select(UserMax).where(
            and_(
                UserMax.is_worked == 1,
                or_(UserMax.vacation_to.is_(None), UserMax.vacation_to <= today),
            )
        )
        users = list(session.scalars(stmt).all())
    available: list[UserMax] = []
    for u in users:
        w = get_today_work_max(u.id)
        if not w.begin:
            available.append(u)
    log.debug("MAX morning users: %s", available)
    return available


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
    evening_kb = evening_menu_max()
    for user in users_to_send:
        try:
            work_is_started = check_work_is_started_max(user.id)
            work_is_ended = check_work_is_ended_max(user.id)
            is_vocation = check_is_vocation_max(user.id)
            dinner_start = check_dinner_start_max(user.id)
            await delete_msg_max(session, user.last_message)
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
                await asyncio.sleep(0.1)
                continue
            res = await send_message(session, user_id=int(user.max_user_id), text=text, buttons=evening_kb)
            mid = mid_from_response(res)
            if mid:
                user.set("last_message", mid)
            log.info("Вечернее сообщение отправлено: %s", user)
            await asyncio.sleep(0.1)
        except Exception as err:
            log.error("Ошибка вечерней отправки %s: %s", user, err, exc_info=False)


async def delay_send_max(user_pk: int, session: aiohttp.ClientSession) -> None:
    user = get_user_max_from_pk(user_pk)
    if not user:
        return
    log.info("MAX delay_send для %s", user)
    work = get_today_work_max(user.id)
    if user.last_message:
        await delete_msg_max(session, user.last_message)
    if not work.end:
        evening_kb = evening_menu_max()
        res = await send_message(
            session, user_id=int(user.max_user_id), text="Рабочий день окончен", buttons=evening_kb
        )
        mid = mid_from_response(res)
        if mid:
            user.set("last_message", mid)
    else:
        log.info("%s уже закончил", user)


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


async def end_task_max(session: aiohttp.ClientSession, scheduler) -> None:
    log.info("MAX завершение дня")
    today = datetime.date.today()
    users_with_empty = evening_users_max()
    now = datetime.datetime.now()
    for user in users_with_empty:
        work = get_today_work_max(user.id)
        if work.last_reaction and now - work.last_reaction > datetime.timedelta(hours=1):
            log.info("%s: прошёл час с последней реакции", user)
            await end_work_max(user, today, work.last_reaction + datetime.timedelta(hours=1), session)
            await delete_msg_max(session, user.last_message)
        elif not work.last_reaction:
            log.info("%s: реакции не было, закрываем в 17:00", user)
            await end_work_max(user, today, datetime.datetime.combine(today, datetime.time(17, 0)), session)
            await delete_msg_max(session, user.last_message)

    users = evening_users_max()
    log.info("MAX осталось на смене: %s", users)
    if users:
        if now.time() > datetime.time(23, 0):
            log.info("MAX: принудительное закрытие в 23:00")
            for user in users:
                await end_work_max(user, today, datetime.datetime.combine(today, datetime.time(23, 0)), session)
        else:
            if max_settings.MAX_REPORT_INTERVAL_MINUTES and max_settings.MAX_REPORT_INTERVAL_MINUTES > 0:
                log.debug(
                    "MAX end_task: без отдельной отсрочки +15 мин (режим MAX_REPORT_INTERVAL_MINUTES)"
                )
            else:
                run_time = datetime.datetime.now() + datetime.timedelta(minutes=15)
                scheduler.add_job(end_task_max, DateTrigger(run_date=run_time), args=(session, scheduler))


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
    group_ok = bool(max_settings.MAX_GROUP_CHAT_ID)
    text = (
        f"[Тест MAX, каждые {interval} мин] {now}\n\n"
        f"Утро (не начали смену сегодня): {n_morning} чел.\n"
        f"Вечер (смена открыта, без конца): до тика {n_evening_before}, после {n_evening_after} чел.\n"
        f"В отпуске: {n_vacation} чел.\n"
        f"Группа для отпусков: {'да' if group_ok else 'нет (MAX_GROUP_CHAT_ID)'}\n\n"
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
    gid = max_settings.MAX_GROUP_CHAT_ID
    if not gid:
        log.warning("MAX_GROUP_CHAT_ID не задан — отпуска в группу не отправлены")
        return
    for user in users_to_send:
        uname = f"@{user.username}" if user.username else "—"
        msg = (
            f"{user.fio}\n"
            f"Username: {uname}\n"
            f"Дата: {today.strftime('%d.%m.%Y')}\n"
            f"Не работает до: {user.vacation_to.strftime('%d.%m.%Y')}\n"
        )
        await send_message(session, chat_id=int(gid), text=msg)
        await asyncio.sleep(0.1)
