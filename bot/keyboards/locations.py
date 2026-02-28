from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def locations_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="T1", callback_data="loc:T1"),
            InlineKeyboardButton(text="T2", callback_data="loc:T2"),
        ],
        [
            InlineKeyboardButton(text="T3", callback_data="loc:T3"),
            InlineKeyboardButton(text="T4", callback_data="loc:T4"),
        ],
        [InlineKeyboardButton(text="Резерв", callback_data="loc:RESERVE")],
    ])