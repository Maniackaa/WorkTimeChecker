import datetime

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


work_start_button = InlineKeyboardButton(text=f'Приступить к работе', callback_data='work_start')
vocation_button = InlineKeyboardButton(text=f'Не работаю', callback_data='vocation_start')
work_end_button_question = InlineKeyboardButton(text=f'❌ Закончить смену?', callback_data='work_end_question')
work_end_button = InlineKeyboardButton(text=f'❌ Закончить смену', callback_data='confirm_work_end')
work_end_button_15 = InlineKeyboardButton(text=f'⏱️ Закончу через 15 минут', callback_data='work_delay_15')
work_end_button_30 = InlineKeyboardButton(text=f'⏰ Закончу через 30 минут', callback_data='work_delay_30')
work_end_button_60 = InlineKeyboardButton(text=f'🕰  Закончу через час', callback_data='work_delay_60')
work_end_button_manual = InlineKeyboardButton(text=f'⌚️ Ввести время окончания смены', callback_data='work_end_manual')
work_continue = InlineKeyboardButton(text=f'✅ Работать дальше ', callback_data='work_continue')

dinner = InlineKeyboardButton(text=f'✅ Перерыв', callback_data='dinner_start')
dinner_end = InlineKeyboardButton(text=f'✅ Закончить перерыв', callback_data='dinner_end')
dinner_end_input = InlineKeyboardButton(text=f'⌚️ Ввести время окончания перерыва ', callback_data='dinner_end_input')
vocation_end = InlineKeyboardButton(text=f'Выйти на работу', callback_data='vocation_end')


def get_dinner_menu(width: int= 1, work_is_started=True, work_is_ended=False, is_vocation=False, dinner_started=False):
    kb_builder: InlineKeyboardBuilder = InlineKeyboardBuilder()
    buttons = []

    buttons.append(dinner_end)
    buttons.append(dinner_end_input)
    kb_builder.row(*buttons, width=width)
    return kb_builder.as_markup()


def get_after_start_menu(width: int= 1, work_is_started=True, work_is_ended=False, is_vocation=False, dinner_started=False):
    kb_builder: InlineKeyboardBuilder = InlineKeyboardBuilder()
    buttons = []
    buttons.append(dinner)
    buttons.append(work_end_button_question)
    kb_builder.row(*buttons, width=width)
    return kb_builder.as_markup()


def get_confirm_end_menu(width: int= 1, work_is_started=True, work_is_ended=False, is_vocation=False, dinner_started=False):
    kb_builder: InlineKeyboardBuilder = InlineKeyboardBuilder()
    buttons = []
    buttons.append(work_end_button)
    buttons.append(work_continue)
    kb_builder.row(*buttons, width=width)
    return kb_builder.as_markup()


def menu_after_work_start(width: int= 1, work_is_started=True, work_is_ended=False, is_vocation=False, dinner_started=False):
    kb_builder: InlineKeyboardBuilder = InlineKeyboardBuilder()
    buttons = []
    buttons.append(dinner)
    buttons.append(work_continue)
    kb_builder.row(*buttons, width=width)
    return kb_builder.as_markup()



def get_menu(width: int, work_is_started=False, work_is_ended=False, is_vocation=False, dinner_started=False) -> InlineKeyboardMarkup:
    kb_builder: InlineKeyboardBuilder = InlineKeyboardBuilder()
    buttons = []
    logger.info(f'work_is_started: {bool(work_is_started)}, work_is_ended: {bool(work_is_ended)},  vocation: {bool(is_vocation)}, dinner_started: {dinner_started}')
    now = datetime.datetime.now()

    if work_is_started and work_is_ended:
        return None

    if work_is_started and not dinner_started:
        # На смене, не на обеде
        logger.info(f'work_is_started and not dinner_started')
        buttons.append(dinner)

    if not work_is_started and not work_is_ended and not is_vocation and not dinner_started:
        # На смену еще не вышел, не в отпуске и не на обеде
        logger.info(f'not work_is_started and not work_is_ended and not is_vocation and not dinner_started')
        buttons.append(work_start_button)
        buttons.append(vocation_button)
    if work_is_started and not work_is_ended and not dinner_started:
        # На смене, не на обеде
        logger.info(f'work_is_started and not work_is_ended and not dinner_started')
        if now.hour >= 17:
            buttons.append(work_end_button_15)
            buttons.append(work_end_button_30)
            buttons.append(work_end_button_60)
        buttons.append(work_end_button_manual)
        buttons.append(work_end_button_question)


    elif work_is_started and dinner_started:
        # На смене, на обеде
        logger.info(f'work_is_started and dinner_started')
        buttons.append(dinner_end)
        buttons.append(dinner_end_input)

    if is_vocation:
        # В отпуске
        logger.info(f'is_vocation')
        buttons.append(vocation_end)

    kb_builder.row(*buttons, width=width)
    return kb_builder.as_markup()


# def evening_menu(dinner_started=False):
#     kb_builder: InlineKeyboardBuilder = InlineKeyboardBuilder()
#     work_end = InlineKeyboardButton(text=f'Закончить смену', callback_data='work_end')
#     b2 = InlineKeyboardButton(text=f'Еще 15 минут', callback_data='work_delay_15')
#     b3 = InlineKeyboardButton(text=f'Еще час', callback_data='work_delay_60')
#     if dinner_started:
#         dinner_buton = InlineKeyboardButton(text=f'Перерыв', callback_data='dinner_start')
#
#     else:
#         dinner_buton = InlineKeyboardButton(text=f'Закончить перерыв', callback_data='dinner_end')
#
#
#     kb_builder.row(work_end, b2, b3, dinner_buton, width=1)
#     return kb_builder.as_markup()


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
