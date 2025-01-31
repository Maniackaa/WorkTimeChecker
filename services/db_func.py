import asyncio
import datetime
from typing import Sequence

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from sqlalchemy import select, delete, RowMapping
from sqlalchemy.orm import joinedload

from config.bot_settings import logger
from database.db import Session, User, Work
from keyboards.keyboards import evening_menu


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
        tg_id = str(user.id)
        username = user.username
        # logger.debug(f'username {username}')
        old_user = check_user(tg_id)
        if old_user:
            # logger.debug('Пользователь есть в базе')
            return old_user
        logger.debug('Добавляем пользователя')
        with Session() as session:
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


def end_work(user_id: int, date, end_time):
    try:
        logger.info(f'user_id: {user_id} date: {date} end_time: {end_time}')
        session = Session(expire_on_commit=False)
        with session:
            q = select(Work).where(Work.user_id == user_id).where(Work.date == date)
            work = session.execute(q).scalars().one_or_none()
            today = datetime.datetime.today()
            if not work:
                work = Work(user_id=user_id, date=today, end=end_time)
                logger.info(f'Создано новое конец смены {user_id} {end_time}')
                session.add(work)
            else:
                logger.info(f'Обновлено конец смены {user_id} {end_time}')
                work.end = end_time
            session.commit()
    except Exception as e:
        raise e


def get_today_work(user_id: int) -> Work:
    session = Session(expire_on_commit=False)
    today = datetime.date.today()
    q = select(Work).where(Work.user_id == user_id).where(Work.date == today)
    work = session.execute(q).scalars().one_or_none()
    return work


def morning_users():
    # Юзеры, которые сегодня еще не вышли на работу
    session = Session(expire_on_commit=False)
    today = datetime.date.today()
    with session:
        query = (
            session.query(User)
            .join(Work, User.id == Work.user, isouter=True)  # Внешнее соединение
            .filter(Work.begin.is_(None))  # Условие, чтобы 'begin' был пустым
            .filter(Work.date == today)  # Условие для сегодняшней даты
            .options(joinedload(User.works))  # Загрузить работы пользователей
        )
        users_with_empty_work_begin_today = query.all()
    logger.debug(f'Юзеры, которые сегодня еще не вышли на работу: {users_with_empty_work_begin_today}')
    return users_with_empty_work_begin_today


def evening_users():
    session = Session(expire_on_commit=False)
    today = datetime.date.today()
    # logger.info(f'Юзеры, которые {today} еще не закончили работу')
    with session:
        query = (
            session.query(User)
            .join(Work, User.id == Work.user_id, isouter=True)
            .filter(Work.begin.is_not(None))
            .filter(Work.end.is_(None))
            .filter(Work.date == today)  # Для фильтрации по дате
            .options(joinedload(User.works))
        )
        users_with_empty_work_end_today = query.all()
    logger.debug(f'Юзеры, которые {today} еще не закончили работу: {users_with_empty_work_end_today}')
    return users_with_empty_work_end_today


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
        logger.info(f'work_is_ended: {work}')
        if not work:
            return False
        if work.end:
            return True
        else:
            return False


async def delete_msg(bot: Bot, chat_id, message_id):
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id, request_timeout=3)
    except Exception as e:
        logger.warning(e)


async def evening_send(bot):
    # Вечерняя отправка если не ушел
    users_to_send = evening_users()
    print(f'users_to_send: {users_to_send}')
    text = f'Рабочий день окончен'
    menu = evening_menu()
    for user in users_to_send:
        try:
            await delete_msg(bot, chat_id=user.tg_id, message_id=user.last_message)
            msg = await bot.send_message(chat_id=user.tg_id, text=text, reply_markup=menu)
            user.set('last_message', msg.message_id)
            logger.info(f'Рабочий день окончен? {user} отправлен')
            await asyncio.sleep(0.1)
        except TelegramForbiddenError as err:
            logger.warning(f'Ошибка отправки сообщения {user}: {err}')
        except Exception as err:
            logger.error(f'Ошибка отправки сообщения {user}: {err}', exc_info=False)


async def delay_send(user_id, bot):
    user = get_user_from_id(user_id)
    logger.info(f'Отправка вечернего сообщения для {user} если еще не закончил')
    work = get_today_work(user.id)
    if user.last_message:
        await delete_msg(bot, chat_id=user.tg_id, message_id=user.last_message)
    if not work.end:
        menu = evening_menu()
        text = f'Рабочий день окончен'
        msg = await bot.send_message(chat_id=user.tg_id, text=text, reply_markup=menu)
        user.set('last_message', msg.message_id)
    else:
        logger.info(f'{user} Уже закончил')


def format_message(user: User, work: Work):

    msg = f"""{user.fio}
    {user.username}
    {work.date}
    {work.begin} - {work.end} 
    {work.end - work.begin} 
    """
    return msg




async def main():
    x = morning_users()
    print(x)
    y = evening_users()
    print(y)



if __name__ == '__main__':
    asyncio.run(main())

