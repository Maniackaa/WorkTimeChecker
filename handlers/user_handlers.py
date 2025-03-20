import datetime

from aiogram import Router, Bot, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, ErrorEvent, ReplyKeyboardRemove, CallbackQuery
from aiogram.utils.payload import decode_payload
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

from api import format_datetime
from config.bot_settings import logger, settings
from database.db import Timer
from keyboards.keyboards import start_kb, get_menu, custom_kb, get_confirm_end_menu, get_dinner_menu, \
    get_after_start_menu
from services.db_func import get_or_create_user, start_work, check_work_is_started, end_work, delete_msg, \
    check_work_is_ended, get_today_work, format_message, check_is_vocation, check_dinner_start

router = Router()
router.message.filter(F.chat.type == "private")


class FSMVocation(StatesGroup):
    vocation_start = State()


class FSMDinner(StatesGroup):
    dinner_end = State()

class FSMWork(StatesGroup):
    work_end = State()


@router.message(CommandStart(deep_link=True))
async def handler(message: Message, command: CommandObject, bot: Bot):
    args = command.args
    # payload = decode_payload(args)
    logger.debug(f'payload: {args}')


@router.message(CommandStart())
async def command_start_process(message: Message, bot: Bot, state: FSMContext):
    await state.clear()
    user = get_or_create_user(message.from_user)
    logger.info('Старт', user=user)
    if user.last_message:
        await delete_msg(bot, chat_id=message.chat.id, message_id=user.last_message)
    work_is_started = check_work_is_started(user.id)
    work_is_ended = check_work_is_ended(user.id)
    is_vocation = check_is_vocation(user.id)
    dinner_start = check_dinner_start(user.id)
    menu_kb = get_menu(1, work_is_started, work_is_ended, is_vocation, dinner_started=dinner_start)
    if work_is_started and work_is_ended:
        msg = await message.answer('Вы уже сегодня отработали')
    elif work_is_started and not work_is_ended:
        msg = await message.answer('Закончить смену?', reply_markup=menu_kb)
        user.set('last_message', msg.message_id)
    elif is_vocation:
        msg = await message.answer(f'Вы в отпуске до {user.vacation_to}', reply_markup=menu_kb)
        user.set('last_message', msg.message_id)
    else:
        msg = await message.answer('Вы на рабочем месте?  Начинаем работу?', reply_markup=menu_kb)
        user.set('last_message', msg.message_id)


@router.callback_query(F.data == 'work_start')
async def work_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    user = get_or_create_user(callback.from_user)
    logger.info(f'{user} work_start')
    today = datetime.date.today()
    now = datetime.datetime.now().replace(microsecond=0)
    work = get_today_work(user.id)
    work_is_started = check_work_is_started(user.id)
    work_is_ended = check_work_is_ended(user.id)
    is_vocation = check_is_vocation(user.id)
    dinner_start = check_dinner_start(user.id)
    menu_kb = get_menu(1, work_is_started, work_is_ended, is_vocation, dinner_started=dinner_start)
    if work_is_started and not work_is_ended:
        await callback.message.answer(f'Вы уже начали смену в {work.begin}', reply_markup=menu_kb)
        return
    if work_is_started and work_is_ended:
        await callback.message.answer(f'Вы уже сегодня отработали')
        return
    start_work(user.id, today, now)

    menu_kb = get_after_start_menu()
    await callback.message.answer(f'Смена начата: {now}')
    msg = await callback.message.answer(f'Выберете действие:', reply_markup=menu_kb)
    user.set('last_message', msg.message_id)


@router.callback_query(F.data == 'work_end_question')
async def work_end_question(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """❌ Закончить смену?"""
    menu = get_confirm_end_menu()
    await callback.message.delete()
    user = get_or_create_user(callback.from_user)
    logger.info(f'{user} ❌ Закончить смену?')
    await callback.message.answer('Завершить смену?', reply_markup=menu)


@router.callback_query(F.data == 'work_continue')
async def work_continue(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Продолжить работать"""
    user = get_or_create_user(callback.from_user)
    logger.info(f'{user} Продолжить работать')
    # work = get_today_work(user.id)
    work_is_started = check_work_is_started(user.id)
    work_is_ended = check_work_is_ended(user.id)
    is_vocation = check_is_vocation(user.id)
    dinner_start = check_dinner_start(user.id)
    menu_kb = get_menu(1, work_is_started=work_is_started, work_is_ended=work_is_ended, is_vocation=is_vocation, dinner_started=dinner_start)
    await callback.message.delete()
    await callback.message.answer('Завершить смену?', reply_markup=menu_kb)


@router.callback_query(F.data == 'confirm_work_end')
async def work_end(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """❌ Точно Закончить смену"""
    await callback.message.delete()
    user = get_or_create_user(callback.from_user)
    logger.info(f'work_end', user=user)
    work = get_today_work(user.id)
    work_is_started = check_work_is_started(user.id)
    work_is_ended = check_work_is_ended(user.id)
    is_vocation = check_is_vocation(user.id)
    dinner_start = check_dinner_start(user.id)
    menu_kb = get_menu(1, work_is_started, work_is_ended, is_vocation, dinner_started=dinner_start)
    if work_is_ended:
        await callback.message.answer(f'Вы уже закончили смену в {work.end}', reply_markup=menu_kb)
        return
    if work_is_started and work_is_ended:
        await callback.message.answer(f'Вы уже сегодня отработали')
        return
    if not work_is_started:
        await callback.message.answer(f'Вы не начали смену')
        return
    today = datetime.date.today()
    now = datetime.datetime.now().replace(microsecond=0)
    await end_work(user, today, now, bot)


@router.callback_query(F.data.startswith('work_delay_'))
async def work_delay(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """⏱️ Закончу через X минут"""
    delay = int(callback.data.split('work_delay_')[1])
    logger.info(f'delay: {delay} {callback.from_user}')
    with Timer('get_or_create_user'):
        user = get_or_create_user(callback.from_user)

    work = get_today_work(user.id)
    work_is_started = check_work_is_started(user.id)
    work_is_ended = check_work_is_ended(user.id)
    is_vocation = check_is_vocation(user.id)
    dinner_start = check_dinner_start(user.id)
    menu_kb = get_menu(1, work_is_started, work_is_ended, is_vocation, dinner_started=dinner_start)
    if user.last_message:
        await delete_msg(bot, chat_id=callback.message.chat.id, message_id=user.last_message)
    if work_is_ended:
        await callback.message.answer(f'Смена окончена: {work.end}')
        return

    # target_time = datetime.datetime.now() + datetime.timedelta(minutes=delay)
    target_time = datetime.datetime.now()
    # target_time_str = format_datetime(datetime.datetime.now() + datetime.timedelta(minutes=delay))
    target_time_str = format_datetime(datetime.datetime.now())
    msg = await callback.message.answer(f'Планируемое врямя окончания: {target_time_str}', reply_markup=menu_kb)
    user.set('last_message', msg.message_id)
    work.set('last_reaction', target_time)


@router.callback_query(F.data == 'vocation_start')
async def vocation_start(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.message.delete()
    await callback.message.answer('Введите дату (дд.мм.гггг) когда планируете вернуться к работе')
    await state.set_state(FSMVocation.vocation_start)


@router.message(StateFilter(FSMVocation.vocation_start))
async def vocation_date(message: Message, state: FSMContext, bot: Bot):
    date_input = message.text.strip()
    try:
        date_obj = datetime.datetime.strptime(date_input, "%d.%m.%Y").date()
        user = get_or_create_user(message.from_user)
        user.set('vacation_to', date_obj)
        kb = custom_kb(1, {'Выйти на работу': 'vocation_end'})
        msg = await message.answer(f"Выход на работу: <b>{date_obj.strftime('%d.%m.%Y')}</b>", reply_markup=kb)
        user.set('last_message', msg.message_id)
        await state.clear()
        await bot.send_message(chat_id=settings.GROUP_ID, text=f'')
    except Exception as e:
        logger.error(e)
        await message.answer(f'Введите дату в формате дд.мм.гггг')


@router.callback_query(F.data == 'vocation_end')
async def vocation_end(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.message.delete()
    user = get_or_create_user(callback.from_user)
    user.set('vacation_to', None)
    await callback.message.answer(f"Вы вышли на работу")


@router.callback_query(F.data == 'dinner_start')
async def dinner_start(callback: CallbackQuery, state: FSMContext, bot: Bot):

    await callback.message.delete()
    user = get_or_create_user(callback.from_user)
    logger.info(f'Перерыв старт {user}')
    work = get_today_work(user.id)
    if not work.dinner_start:
        logger.info(f'Перерыв не начат {user}')
        now = datetime.datetime.now().replace(microsecond=0)
        work.set('dinner_start', now)
        work.set('last_reaction', now)
        await callback.message.answer(f'Перерыв начат: {now}')
        msg = await callback.message.answer(f'Закончите перерыв', reply_markup=get_dinner_menu())
        user.set('last_message', msg.message_id)
    else:
        logger.info(f'Перерыв уже начат {user} в {work.dinner_start}')
        await callback.message.answer(f'Перерыв уже начат в {work.dinner_start}')


@router.callback_query(F.data == 'dinner_end')
async def dinner_end(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.message.delete()
    user = get_or_create_user(callback.from_user)
    logger.info(f'{user} dinner_end')
    work = get_today_work(user.id)
    now = datetime.datetime.now().replace(microsecond=0)
    if work.dinner_start and not work.dinner_end:
        dinner_time = (now - work.dinner_start).total_seconds()
        work.set('total_dinner', work.total_dinner + dinner_time)
        work.set('dinner_start', None)
        work.set('dinner_end', None)
        work.set('last_reaction', None)
        work_is_started = check_work_is_started(user.id)
        work_is_ended = check_work_is_ended(user.id)
        is_vocation = check_is_vocation(user.id)
        dinner_start = check_dinner_start(user.id)
        menu = get_menu(1, work_is_started, work_is_ended, is_vocation, dinner_started=dinner_start)
        await callback.message.answer(f'Перерыв окончен: {now}')
        msg = await callback.message.answer(f'Перерыв окончен', reply_markup=menu)
        user.set('last_message', msg.message_id)


@router.callback_query(F.data == 'dinner_end_input')
async def dinner_end_input(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.message.delete()
    await callback.message.answer('Введите время окнчания перерыва: ЧЧ:ММ')
    await state.set_state(FSMDinner.dinner_end)


@router.message(StateFilter(FSMDinner.dinner_end))
async def dinner_end_input(message: Message, state: FSMContext, bot: Bot):
    time_input = message.text.strip()
    try:
        user = get_or_create_user(message.from_user)
        work = get_today_work(user.id)
        if work.dinner_start and not work.dinner_end:
            today = datetime.date.today()
            time_obj = datetime.datetime.strptime(time_input, "%H:%M").time()
            dinner_end = datetime.datetime.combine(today, time_obj)
            if dinner_end < work.dinner_start:
                await message.answer('Время окончания не может быть ранее начала')
                return
            dinner_time = (dinner_end - work.dinner_start).total_seconds()
            logger.info(f'dinner_time: {dinner_time}')
            work.set('total_dinner', work.total_dinner + dinner_time)
            work.set('dinner_start', None)
            work.set('dinner_end', None)
            work_is_started = check_work_is_started(user.id)
            work_is_ended = check_work_is_ended(user.id)
            is_vocation = check_is_vocation(user.id)
            dinner_start = check_dinner_start(user.id)
            menu = get_menu(1, work_is_started, work_is_ended, is_vocation, dinner_started=dinner_start)
            await message.answer(f'Перерыв окончен: {dinner_end}')
            msg = await message.answer(f'Закончить смену?', reply_markup=menu)
            user.set('last_message', msg.message_id)
            await state.clear()
    except Exception as e:
        logger.error(e)
        await message.answer(f'Введите время в формате ЧЧ:ММ')



@router.callback_query(F.data == 'work_end_manual')
async def work_end_manual(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.message.delete()
    await callback.message.answer('Введите время окончания работы: ЧЧ:ММ')
    await state.set_state(FSMWork.work_end)


@router.message(StateFilter(FSMWork.work_end))
async def work_end_manual_input(message: Message, state: FSMContext, bot: Bot):
    time_input = message.text.strip()
    try:
        user = get_or_create_user(message.from_user)
        work = get_today_work(user.id)
        if work.begin and not work.end:
            today = datetime.date.today()
            time_obj = datetime.datetime.strptime(time_input, "%H:%M").time()
            work_end = datetime.datetime.combine(today, time_obj)
            if work_end > datetime.datetime.now():
                await message.answer('Время окончания не может быть позже чем сейчас')
                return

            logger.info(f'work_end: {work_end}')
            await message.answer(f'Смена окончена: {format_datetime(work_end)}')
            work.set('end', work_end)
            await state.clear()

            work = get_today_work(user.id)
            text = format_message(user, work)
            await bot.send_message(chat_id=settings.GROUP_ID, text=text)
    except Exception as e:
        logger.error(e)
        await message.answer(f'Введите время в формате ЧЧ:ММ')