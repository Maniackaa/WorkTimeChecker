import datetime

from aiogram import Router, Bot, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ErrorEvent, ReplyKeyboardRemove, CallbackQuery
from aiogram.utils.payload import decode_payload
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

from config.bot_settings import logger, settings
from database.db import Timer
from keyboards.keyboards import start_kb, get_menu
from services.db_func import get_or_create_user, start_work, check_work_is_started, end_work, delete_msg, evening_send, \
    delay_send, check_work_is_ended, get_today_work, format_message

router = Router()


@router.message(CommandStart(deep_link=True))
async def handler(message: Message, command: CommandObject, bot: Bot):
    args = command.args
    # payload = decode_payload(args)
    logger.debug(f'payload: {args}')


@router.message(CommandStart())
async def command_start_process(message: Message, bot: Bot):
    user = get_or_create_user(message.from_user)
    logger.info('Старт', user=user)
    if user.last_message:
        await delete_msg(bot, chat_id=message.chat.id, message_id=user.last_message)
    work_is_started = check_work_is_started(user.id)
    work_is_ended = check_work_is_ended(user.id)

    menu_kb = get_menu(1, work_is_started)
    if work_is_started and work_is_ended:
        msg = await message.answer('Вы уже сегодня отработали')
    elif work_is_started:
        msg = await message.answer('Закончить смену?', reply_markup=menu_kb)
        user.set('last_message', msg.message_id)
    else:
        msg = await message.answer('Вы на рабочем месте?  Начинаем работу?', reply_markup=menu_kb)
        user.set('last_message', msg.message_id)


@router.callback_query(F.data == 'work_start')
async def work_start(callback: CallbackQuery, state: FSMContext):
    user = get_or_create_user(callback.from_user)
    logger.info(f'work_start', user=user)
    today = datetime.date.today()
    now = datetime.datetime.now().replace(microsecond=0)
    start_work(user.id, today, now)
    menu = get_menu(1, work_is_started=True)
    await callback.message.answer(f'Смена начата: {now}', reply_markup=menu)
    await callback.message.delete()


@router.callback_query(F.data == 'work_end')
async def work_end(callback: CallbackQuery, state: FSMContext):
    user = get_or_create_user(callback.from_user)
    logger.info(f'work_end', user=user)

    today = datetime.date.today()
    now = datetime.datetime.now().replace(microsecond=0)
    end_work(user.id, today, now)
    # menu = get_menu(1, work_is_started=True)
    await callback.message.answer(f'Смена окончена: {now}')
    await callback.message.delete()

    work = get_today_work(user.id)
    text = format_message(user, work)
    await callback.bot.send_message(chat_id=settings.GROUP_ID, text=text)


@router.callback_query(F.data.startswith('work_delay_'))
async def work_end(callback: CallbackQuery, state: FSMContext, bot: Bot):
    delay = int(callback.data.split('work_delay_')[1])
    logger.info(f'delay: {delay}')
    with Timer('get_or_create_user'):
        user = get_or_create_user(callback.from_user)
    menu = get_menu(1, work_is_started=True, work_is_ended=False)

    if user.last_message:
        with Timer('delete_msg'):
            await delete_msg(bot, chat_id=callback.message.chat.id, message_id=user.last_message)
    msg = await callback.message.answer(f'Рабочий день окончен', reply_markup=menu)
    user.set('last_message', msg.message_id)
    user.set('last_reaction', datetime.datetime.now())
    run_time = datetime.datetime.now() + datetime.timedelta(minutes=delay)
    scheduler = AsyncIOScheduler()
    scheduler.add_job(delay_send, DateTrigger(run_date=run_time), args=(user.id, callback.bot,))
    scheduler.start()
    logger.info(f'Добавлена задача delay_send для {user}: {run_time}')





