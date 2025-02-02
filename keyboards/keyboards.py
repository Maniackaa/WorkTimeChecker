from aiogram.types import KeyboardButton, ReplyKeyboardMarkup,\
    InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from config.bot_settings import logger
from database.db import User

kb = [
    [KeyboardButton(text="/start")],
    ]

start_bn: ReplyKeyboardMarkup = ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


def custom_kb(width: int, buttons_dict: dict, back='', group='', menus='') -> InlineKeyboardMarkup:
    kb_builder: InlineKeyboardBuilder = InlineKeyboardBuilder()
    buttons = []
    for key, val in buttons_dict.items():
        callback_button = InlineKeyboardButton(
            text=key,
            callback_data=val)
        buttons.append(callback_button)
    kb_builder.row(*buttons, width=width)
    if group:
        group_btn = InlineKeyboardButton(text='Обсудить в группе', url=group)
        kb_builder.row(group_btn)
    if menus:
        for menu in menus:
            item_btn = InlineKeyboardButton(text=menu[0], callback_data=f'menu_page_{menu[1]}')
            kb_builder.row(item_btn)
    if back:
        kb_builder.row(InlineKeyboardButton(text=back, callback_data='cancel'))
    return kb_builder.as_markup()


def get_menu(width: int, work_is_started=False, work_is_ended=False, is_vocation=False, dinner_started=False) -> InlineKeyboardMarkup:
    kb_builder: InlineKeyboardBuilder = InlineKeyboardBuilder()
    buttons = []
    logger.info(f'work_is_started: {bool(work_is_started)}, work_is_ended: {bool(work_is_ended)},  vocation: {bool(is_vocation)}, dinner_started: {dinner_started}')
    if work_is_started and work_is_ended:
        return None
    if not work_is_started and not work_is_ended and not is_vocation and not dinner_started:
        work_start = InlineKeyboardButton(text=f'Приступить к работе', callback_data='work_start')
        vocation = InlineKeyboardButton(text=f'Не работаю', callback_data='vocation_start')
        buttons.append(work_start)
        buttons.append(vocation)
    if work_is_started and not work_is_ended and not dinner_started:
        work_end = InlineKeyboardButton(text=f'Закончить смену', callback_data='work_end')
        buttons.append(work_end)
    if work_is_started and not dinner_started:
        dinner = InlineKeyboardButton(text=f'Перерыв', callback_data='dinner_start')
        buttons.append(dinner)
    elif work_is_started and dinner_started:
        dinner_end = InlineKeyboardButton(text=f'Закончить перерыв', callback_data='dinner_end')
        dinner_end_input = InlineKeyboardButton(text=f'Перерыв уже окончен', callback_data='dinner_end_input')
        buttons.append(dinner_end)
        buttons.append(dinner_end_input)
    if is_vocation:
        logger.info(f'vocation')
        vocation_end = InlineKeyboardButton(text=f'Выйти на работу', callback_data='vocation_end')
        buttons.append(vocation_end)

    kb_builder.row(*buttons, width=width)
    return kb_builder.as_markup()


def evening_menu():
    kb_builder: InlineKeyboardBuilder = InlineKeyboardBuilder()
    work_end = InlineKeyboardButton(text=f'Закончить смену', callback_data='work_end')
    b2 = InlineKeyboardButton(text=f'Еще 15 минут', callback_data='work_delay_15')
    b3 = InlineKeyboardButton(text=f'Еще час', callback_data='work_delay_60')
    kb_builder.row(work_end, b2, b3, width=1)
    return kb_builder.as_markup()


PREFIX = '.Text'
kb_builder: InlineKeyboardBuilder = InlineKeyboardBuilder()
work_start = InlineKeyboardButton(text=f'Приступить к работе', callback_data='work_start')
start_kb = kb_builder.row(work_start).as_markup()


yes_no_kb_btn = {
    'Да': 'yes',
    'Нет': 'no',
}
yes_no_kb = custom_kb(2, yes_no_kb_btn)

confirm_kb_btn = {
    'Отменить': 'cancel',
    'Подтвердить': 'confirm',
}
confirm_kb = custom_kb(2, confirm_kb_btn)
