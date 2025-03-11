import asyncio
import datetime
from typing import Sequence

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from sqlalchemy import select, delete, RowMapping, and_, or_, not_, exists
from sqlalchemy.orm import joinedload

from config.bot_settings import logger, settings
from database.db import Session, User, Work
from keyboards.keyboards import get_menu


def check_user(id):
    """Возвращает найденных пользователей по tg_id"""
    # logger.debug(f'Ищем юзера {id}')
    with Session() as session:
        user: User = session.query(User).filter(User.tg_id == str(id)).one_or_none()
        # logger.debug(f'Результат: {user}')
        return user


def get_user_from_id(pk) -> User:
    session = Session(expire_on_commit=False)
    with session:
        q = select(User).filter(User.id == pk)
        print(q)
        user = session.execute(q).scalars().one_or_none()
        return user


def get_or_create_user(user) -> User:
    """Из юзера ТГ возвращает сущестующего User ли создает его"""
    try:
        session = Session(expire_on_commit=False)
        with session:
            tg_id = str(user.id)
            username = user.username
            old_user = check_user(tg_id)
            if old_user:
                # logger.debug('Пользователь есть в базе')
                if not old_user.username or username != old_user.username:
                    old_user.username = username
                if not old_user.fio:
                    old_user.fio = user.full_name
                session.add(old_user)
                session.commit()
                return old_user
            logger.debug('Добавляем пользователя')

            new_user = User(tg_id=tg_id,
                            username=username,
                            register_date=datetime.datetime.now(),
                            fio=user.full_name
                            )
            session.add(new_user)
            session.commit()
            logger.debug(f'Пользователь создан: {new_user}')
        return new_user
    except Exception as err:
        logger.error('Пользователь не создан', exc_info=True)


def start_work(user_id: int, date, start_time):
    # Начинаем смену
    try:
        logger.info(f'user_id: {user_id} date: {date} start_time: {start_time}')
        session = Session(expire_on_commit=False)
        with session:
            q = select(Work).where(Work.user_id == user_id).where(Work.date == date)
            work = session.execute(q).scalars().one_or_none()
            today = datetime.datetime.today()
            if not work:
                work = Work(user_id=user_id, date=today, begin=start_time)
                logger.info(f'Создано новое начало смены {user_id} {start_time}')
                session.add(work)
            else:
                logger.info(f'Обновлено начало смены {user_id} {start_time}')
                work.begin = start_time
            session.commit()
    except Exception as e:
        raise e


async def end_work(user: User, date, end_time, bot):
    # Записываем конец смены
    try:
        logger.info(f'user: {user} date: {date} end_time: {end_time}')
        session = Session(expire_on_commit=False)
        with session:
            q = select(Work).where(Work.user_id == user.id).where(Work.date == date)
            work = session.execute(q).scalars().one_or_none()
            logger.info(f'Обновлено конец смены {user} {end_time}')
            work.end = end_time
            session.commit()

        work = get_today_work(user.id)
        text = format_message(user, work)
        await bot.send_message(chat_id=settings.GROUP_ID, text=text)
        await bot.send_message(chat_id=user.tg_id, text=f'Смена окончена: {end_time}')

    except Exception as e:
        logger.warning(f'Ошибка при окончании смены для {user} {date}, {end_time}')


def get_today_work(user_id: int) -> Work:
    # Возвращает сегоднящнюю смену
    session = Session(expire_on_commit=False)
    today = datetime.date.today()
    with session:
        q = select(Work).where(Work.user_id == user_id).where(Work.date == today)
        work = session.execute(q).scalars().one_or_none()
    if not work:
        work = Work(user_id=user_id, date=today)
    return work


def morning_users():
    # Юзеры, которые сегодня еще не вышли на работу
    try:
        session = Session(expire_on_commit=False)
        today = datetime.date.today()
        with session:
            stmt = select(User).where(
                and_(
                    User.is_worked == 1,
                    or_(
                        User.vacation_to == None,
                        User.vacation_to <= today
                    ),
                )
            ).outerjoin(Work, and_(Work.user_id == User.id, Work.date == today))

            users = session.scalars(stmt).all()
            available_users = []
            for user in users:
                if not user.works:
                    available_users.append(user)
                else:
                    last_work = user.works[-1]
                    # Если сегодня нет работы или есть, но не началась
                    if last_work.date != today or (last_work.date == today and not last_work.begin):
                        available_users.append(user)

        logger.debug(f'Юзеры, которые сегодня еще не вышли на работу: {available_users}')
        return available_users
    except Exception as e:
        logger.error(e)


def evening_users():
    session = Session(expire_on_commit=False)
    today = datetime.date.today()
    with session:
        query = (
            session.query(User)
            .join(Work, User.id == Work.user_id, isouter=True)
            .filter(Work.begin.is_not(None))
            .filter(Work.end.is_(None))
            .filter(Work.date == today)
            .options(joinedload(User.works))
        )
        users_with_empty_work_end_today = query.all()
    logger.debug(f'Юзеры, которые {today} еще не закончили работу ({len(users_with_empty_work_end_today)}): {users_with_empty_work_end_today}')
    return users_with_empty_work_end_today

def all_evening_users():
    session = Session(expire_on_commit=False)
    today = datetime.date.today()
    # logger.info(f'Юзеры, которые {today} еще не закончили работу')
    with session:
        query = (
            session.query(User)
            .join(Work, User.id == Work.user_id, isouter=True)
            .filter(Work.begin.is_not(None))
            .filter(Work.end.is_(None))
            .filter(Work.date == today)
            .options(joinedload(User.works))
        )
        users_with_empty_work_end_today = query.all()
    logger.debug(f'Юзеры, которые {today} еще не закончили работу: {users_with_empty_work_end_today}')
    return users_with_empty_work_end_today


def vocation_users():
    session = Session(expire_on_commit=False)
    today = datetime.date.today()
    # logger.info(f'Юзеры, которые {today} еще не закончили работу')
    with session:
        query = (
            session.query(User).where(User.vacation_to > today)
        )
        users = query.all()
        logger.info(f'Юзеры в отпуске: {users}')
    return users


def check_work_is_started(user_id: int):
    session = Session(expire_on_commit=False)
    today = datetime.date.today()
    with session:
        q = (session.query(Work).filter(Work.user_id == user_id).filter(Work.date == today))
        work = q.one_or_none()
        logger.info(f'work_is_started: {work}')
        if not work:
            return False
        if work.begin:
            return True
        else:
            return False


def check_work_is_ended(user_id: int):
    session = Session(expire_on_commit=False)
    today = datetime.date.today()
    with session:
        q = (session.query(Work).filter(Work.user_id == user_id).filter(Work.date == today))
        work = q.one_or_none()

        if not work:
            logger.info(f'Не начинал работать')
            return False
        if work.end:
            logger.info(f'work_is_ended: {work.end}')
            return True
        else:
            logger.info(f'work_is_ended: {work.end}')
            return False


def check_is_vocation(user_id: int):
    # Проверка в отпуске ли человек
    session = Session(expire_on_commit=False)
    today = datetime.date.today()
    with session:
        q = (session.query(User).filter(User.id == user_id))
        user = q.one_or_none()
        logger.info(f'user: {user}')
        if user.vacation_to and user.vacation_to > today:
            return True
        return False


def check_dinner_start(user_id: int):
    # Проверка начала обеда
    session = Session(expire_on_commit=False)
    today = datetime.date.today()
    with session:
        q = (session.query(Work).filter(Work.user_id == user_id).filter(Work.date == today))
        work = q.one_or_none()
        if work:
            return work.dinner_start and not work.dinner_end
        return False


async def delete_msg(bot: Bot, chat_id, message_id):
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id, request_timeout=3)
    except Exception as e:
        logger.warning(e)


def format_message(user: User, work: Work):
    work_durations = calculate_work_durations(user.id)
    msg = f"""{user.fio}
    Username: @{user.username}
    Дата: {work.date.strftime('%d.%m.%Y')}
    Начало: {work.begin.time()}
    Окончание: {work.end.time()} 
    Перерывы: {work.total_dinner // 60} мин. 
    Продолжительность:
    Сегодня: {work_durations['today']}
    Неделя: {work_durations['week']}
    Месяц: {work_durations['month']}
    """
    return msg


def format_total_time(total_seconds):
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    return f"{hours} часов {minutes} минут"


def calculate_work_durations(user_id: int):
    """
    Вычисляет продолжительность рабочего времени для пользователя за сегодня, неделю и месяц.
    """
    today = datetime.date.today()
    now = datetime.datetime.now()
    start_of_week = today - datetime.timedelta(days=today.weekday())
    start_of_month = today.replace(day=1)

    # Функция для расчета общей продолжительности
    def calculate_total_seconds(work_list):
        total_seconds = 0
        for work in work_list:
            if work.begin and work.end:
                total_seconds += (work.end - work.begin).total_seconds()
            elif work.begin and not work.end:
              total_seconds += (now - work.begin).total_seconds()
            if work.total_dinner:
                 total_seconds -= work.total_dinner
        return format_total_time(total_seconds)

    session = Session(expire_on_commit=False)
    with session:
        # За сегодня
        stmt_today = select(Work).where(Work.user_id == user_id, Work.date == today)
        works_today = session.scalars(stmt_today).all()
        total_seconds_today = calculate_total_seconds(works_today)


        # За неделю
        stmt_week = select(Work).where(Work.user_id == user_id,
                                       Work.date >= start_of_week,
                                       Work.date <= today)
        works_week = session.scalars(stmt_week).all()
        total_seconds_week = calculate_total_seconds(works_week)

        # За месяц
        stmt_month = select(Work).where(Work.user_id == user_id,
                                        Work.date >= start_of_month,
                                        Work.date <= today)
        works_month = session.scalars(stmt_month).all()
        total_seconds_month = calculate_total_seconds(works_month)

    return {
        "today": total_seconds_today,
        "week": total_seconds_week,
        "month": total_seconds_month,
    }

async def main():
    x = morning_users()
    print(x)
    # y = evening_users()
    # print(y)
    # a = calculate_work_durations(1)
    # print(a)
    b = vocation_users()
    print(b)



if __name__ == '__main__':
    asyncio.run(main())

