from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def qty_kb(ctx: str, qty: int) -> InlineKeyboardMarkup:
    # ctx = "full:<item_id>" або "custom:<item_id>"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➖", callback_data=f"qty:minus:{ctx}"),
                InlineKeyboardButton(text=str(qty), callback_data="noop"),
                InlineKeyboardButton(text="➕", callback_data=f"qty:plus:{ctx}"),
            ],
            [
                InlineKeyboardButton(text="✅ Готово", callback_data=f"qty:ok:{ctx}"),
                InlineKeyboardButton(text="⬅ Назад", callback_data=f"qty:back:{ctx}"),
            ],
        ]
    )