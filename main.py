import asyncio
import datetime
import time

from aiogram.exceptions import TelegramForbiddenError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import ExceptionTypeFilter
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation
from aiogram.fsm.storage.redis import DefaultKeyBuilder, RedisStorage
from aiogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeChat
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from config.bot_settings import logger, settings
from handlers import user_handlers, action_handlers
from handlers.user_handlers import delete_msg
from keyboards.keyboards import get_menu, evening_menu
from services.db_func import morning_users, evening_users, evening_send, get_today_work, end_work, vocation_users, \
    all_evening_users


async def set_commands(bot: Bot):
    commands = [
        BotCommand(
            command="start",
            description="Start",
        ),
    ]

    admin_commands = commands.copy()
    admin_commands.append(
        BotCommand(
            command="admin",
            description="Admin panel",
        )
    )

    await bot.set_my_commands(commands=commands, scope=BotCommandScopeDefault())
    for admin_id in settings.ADMIN_IDS:
        try:
            await bot.set_my_commands(
                commands=admin_commands,
                scope=BotCommandScopeChat(
                    chat_id=admin_id,
                ),
            )
        except Exception as err:
            logger.info(f'Админ id {admin_id}  ошибочен')


async def morning_send(bot):
    # Утренняя отправка если не вышел
    users_to_send = morning_users()
    print(f'users_to_send: {users_to_send}')
    text = f'Вы на рабочем месте?  Начинаем работу?'
    menu = get_menu(1, work_is_started=False, work_is_ended=False)
    for user in users_to_send:
        try:
            await delete_msg(bot, chat_id=user.tg_id, message_id=user.last_message)
            msg = await bot.send_message(chat_id=user.tg_id, text=text, reply_markup=menu)
            user.set('last_message', msg.message_id)
            logger.info(f'Вы на рабочем месте?  Начинаем работу? {user} отправлен')
            await asyncio.sleep(0.1)
        except TelegramForbiddenError as err:
            logger.warning(f'Ошибка отправки сообщения {user}: {err}')
        except Exception as err:
            logger.error(f'Ошибка отправки сообщения {user}: {err}', exc_info=False)


async def end_task(bot, scheduler):
    # Завершение дня.
    logger.info(f'Завершение дня')
    today = datetime.date.today()
    users_with_empty_work_end_today = evening_users()
    logger.info(f'На смене: {users_with_empty_work_end_today}')
    now = datetime.datetime.now()
    for user in users_with_empty_work_end_today:
        work = get_today_work(user.id)
        if work.last_reaction and now - work.last_reaction > datetime.timedelta(hours=1):
            logger.info(f'{user} Прошло боле часа с последней реакции')
            await end_work(user, today, work.last_reaction + datetime.timedelta(hours=1), bot)
            await delete_msg(bot, chat_id=user.tg_id, message_id=user.last_message)
        if not work.last_reaction:
            logger.info(f'{user} Реакции не было. Закрываем в 17.00')
            await end_work(user, today, datetime.datetime.combine(today, datetime.time(17, 0)), bot)
            await delete_msg(bot, chat_id=user.tg_id, message_id=user.last_message)

    # Чё осталось
    users = all_evening_users()
    logger.info(f'Осталось на смене: {users}')
    if users:
        if now.time() > datetime.time(23, 59):
            logger.info(f'Хватит работать!')
            for user in users:
                await end_work(user, today, datetime.datetime.combine(today, datetime.time(23, 59)), bot)
        else:
            run_time = datetime.datetime.now() + datetime.timedelta(minutes=15)
            scheduler.add_job(end_task, DateTrigger(run_date=run_time), args=(bot, scheduler))


async def vocation_task(bot: Bot):
    # Отправка по отпускникам
    users_to_send = vocation_users()
    today = datetime.date.today()
    for user in users_to_send:
        msg = f"""{user.fio}
    Username: @{user.username}
    Дата: {today.strftime('%d.%m.%Y')}
    Не работает до: {user.vacation_to.strftime('%d.%m.%Y')}
    """
        await bot.send_message(chat_id=settings.GROUP_ID, text=msg)
        await asyncio.sleep(0.1)


def set_scheduled_jobs(scheduler, bot, *args, **kwargs):
    # scheduler.add_job(morning_send, "interval", seconds=5, args=(bot,))
    scheduler.add_job(morning_send, CronTrigger(hour=7, minute=59), args=(bot,))
    scheduler.add_job(morning_send, CronTrigger(hour=8, minute=15), args=(bot,))
    scheduler.add_job(morning_send, CronTrigger(hour=8, minute=30), args=(bot,))
    scheduler.add_job(morning_send, CronTrigger(hour=8, minute=45), args=(bot,))
    scheduler.add_job(morning_send, CronTrigger(hour=9, minute=00), args=(bot,))

    scheduler.add_job(evening_send, CronTrigger(hour=17, minute=00), args=(bot,))
    # scheduler.add_job(evening_send, CronTrigger(hour=14, minute=56), args=(bot,))
    # scheduler.add_job(evening_send, "interval", seconds=60, args=(bot,))
    scheduler.add_job(end_task, CronTrigger(hour=18, minute=1, second=0), args=(bot, scheduler))
    scheduler.add_job(vocation_task, CronTrigger(hour=18, minute=0, second=0), args=(bot,))
    # scheduler.add_job(vocation_task, "interval", seconds=5, args=(bot,))


async def main():
    if settings.USE_REDIS:
        storage = RedisStorage.from_url(
            url=f"redis://{settings.REDIS_HOST}",
            connection_kwargs={
                "db": 0,
            },
            key_builder=DefaultKeyBuilder(with_destiny=True),
        )
    else:
        storage = MemoryStorage()

    bot = Bot(token=settings.BOT_TOKEN,  default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=storage, events_isolation=SimpleEventIsolation())

    try:
        dp.include_router(user_handlers.router)
        dp.include_router(action_handlers.router)

        await set_commands(bot)
        # await bot.get_updates(offset=-1)
        await bot.delete_webhook(drop_pending_updates=True)
        await bot.send_message(chat_id=settings.ADMIN_IDS[0], text='Бот запущен')

        scheduler = AsyncIOScheduler()
        set_scheduled_jobs(scheduler, bot)
        scheduler.start()
        # await asyncio.create_task(evening_send(bot))

        # await bot.send_message(chat_id=config.tg_bot.GROUP_ID, text='Бот запущен', reply_markup=begin_kb)
        await dp.start_polling(bot, config=settings)
    finally:
        await dp.fsm.storage.close()
        await bot.session.close()


try:
    asyncio.run(main())
except (KeyboardInterrupt, SystemExit):
    logger.error("Bot stopped!")
