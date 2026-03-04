from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)


def main_menu_kb(has_phone: bool = False, show_order: bool = True) -> ReplyKeyboardMarkup:
    """Bottom reply keyboard (bar).
    show_order=False -> hide 'Замовити' while user is inside inline ordering flow.
    """
    rows = []
    if show_order:
        rows.append([KeyboardButton(text="🥗 Замовити")])

    if not has_phone:
        rows.append([KeyboardButton(text="📞 Поділитися номером", request_contact=True)])

    # if everything hidden, still return a minimal keyboard to avoid UI glitches
    return ReplyKeyboardMarkup(keyboard=rows or [[KeyboardButton(text="🏠 Меню")]], resize_keyboard=True)


def _short(text: str, limit: int = 26) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def menu_kb(items: list[dict], cart: dict) -> InlineKeyboardMarkup:
    """
    items формат:
      [
        {
          "id": <menu_item_id>,
          "title": "...",
          "positions": [
             {"key": "full:12", "title": "Комплекс повністю", "price": 150},
             {"key": "p1:12", "title": "Перша страва", "price": 70},
             ...
          ]
        }
      ]

    cart формат:
      {"full:12": 1, "p1:12": 2}
    """
    kb: list[list[InlineKeyboardButton]] = []
    cart = cart or {}

    for item in items or []:
        positions = item.get("positions") or []
        if not positions:
            continue

        item_title = (item.get("title") or "").strip() or "Меню"
        kb.append([InlineKeyboardButton(text=_short(item_title), callback_data="noop")])

        row: list[InlineKeyboardButton] = []

        for pos in positions:
            key = str(pos.get("key") or "")
            if not key:
                continue

            title = _short(pos.get("title", ""), 22)
            price = int(pos.get("price") or 0)

            qty = int(cart.get(key, 0) or 0)
            mark = "✅ " if qty > 0 else ""

            row.append(InlineKeyboardButton(
                text=f"{mark}{title} — {price}₴",
                callback_data=f"pick:{key}"   # <- головне: pick:<key>
            ))

            if len(row) == 2:
                kb.append(row)
                row = []

        if row:
            kb.append(row)

    kb.append([InlineKeyboardButton(text="✅ Підтвердити замовлення", callback_data="confirm")])
    kb.append([InlineKeyboardButton(text="📍 Змінити локацію", callback_data="change_location")])

    return InlineKeyboardMarkup(inline_keyboard=kb)


def qty_kb(ctx: str, qty: int) -> InlineKeyboardMarkup:
    """
    ctx = 'full:12' | 'p1:12' | ...
    """
    qty = max(1, int(qty or 1))
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➖", callback_data=f"qty:minus:{ctx}"),
            InlineKeyboardButton(text=str(qty), callback_data="noop"),
            InlineKeyboardButton(text="➕", callback_data=f"qty:plus:{ctx}"),
        ],
        [InlineKeyboardButton(text="Готово ✅", callback_data=f"qty:ok:{ctx}")],
    ])


def after_confirm_kb(is_subscribed: bool, can_cancel: bool = True) -> InlineKeyboardMarkup:
    sub_text = "Відписатися" if is_subscribed else "Підписатися"
    sub_cb = "sub:off" if is_subscribed else "sub:on"

    rows = [
        [InlineKeyboardButton(text="Зробити ще заказ", callback_data="order:more")],
        [InlineKeyboardButton(text="Змінити місце доставки", callback_data="change_location")],
        [InlineKeyboardButton(text="Звʼязок з адміністратором", callback_data="admin:contact")],
    ]
    if can_cancel:
        rows.append([InlineKeyboardButton(text="❌ Скасувати замовлення", callback_data="order:cancel")])

    rows.append([InlineKeyboardButton(text=sub_text, callback_data=sub_cb)])
    return InlineKeyboardMarkup(inline_keyboard=rows)



