from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)


def main_menu_kb(has_phone: bool = False, show_order: bool = True) -> ReplyKeyboardMarkup:
    rows = []
    if show_order:
        rows.append([KeyboardButton(text="🥗 Замовити")])

    if not has_phone:
        rows.append([KeyboardButton(text="📞 Поділитися номером", request_contact=True)])

    return ReplyKeyboardMarkup(keyboard=rows or [[KeyboardButton(text="🏠 Меню")]], resize_keyboard=True)


def _short(text: str, limit: int = 26) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def menu_kb(items: list[dict], frozen_items: list[dict], cart: dict) -> InlineKeyboardMarkup:
    kb: list[list[InlineKeyboardButton]] = []
    cart = cart or {}

    for item in items or []:
        positions = item.get("positions") or []
        if not positions:
            continue

        full_pos = None
        other_positions = []

        for pos in positions:
            key = str(pos.get("key") or "")
            if not key:
                continue

            if key.startswith("full:"):
                full_pos = pos
            else:
                other_positions.append(pos)

        if full_pos:
            key = str(full_pos.get("key") or "")
            title = _short(full_pos.get("title", ""), 22)
            price = int(full_pos.get("price") or 0)

            qty = int(cart.get(key, 0) or 0)
            mark = "✅ " if qty > 0 else ""

            kb.append([
                InlineKeyboardButton(
                    text=f"{mark}{title} — {price}₴",
                    callback_data=f"pick:{key}"
                )
            ])

        row: list[InlineKeyboardButton] = []

        for pos in other_positions:
            key = str(pos.get("key") or "")
            title = _short(pos.get("title", ""), 22)
            price = int(pos.get("price") or 0)

            qty = int(cart.get(key, 0) or 0)
            mark = "✅ " if qty > 0 else ""

            row.append(
                InlineKeyboardButton(
                    text=f"{mark}{title} — {price}₴",
                    callback_data=f"pick:{key}"
                )
            )

            if len(row) == 2:
                kb.append(row)
                row = []

        if row:
            kb.append(row)

    if frozen_items:
        kb.append([InlineKeyboardButton(text="🧊 Заморожені продукти", callback_data="noop")])

        for fr in frozen_items:
            pos = fr.get("position") or {}
            key = str(pos.get("key") or "")
            if not key:
                continue

            title = _short(pos.get("title", ""), 22)
            price = int(pos.get("price") or 0)

            qty = int(cart.get(key, 0) or 0)
            mark = "✅ " if qty > 0 else ""

            kb.append([
                InlineKeyboardButton(
                    text=f"{mark}{title} — {price}₴",
                    callback_data=f"pick:{key}"
                )
            ])

    kb.append([InlineKeyboardButton(text="✅ Підтвердити замовлення", callback_data="confirm")])
    kb.append([InlineKeyboardButton(text="📍 Змінити локацію", callback_data="change_location")])

    return InlineKeyboardMarkup(inline_keyboard=kb)


def qty_kb(ctx: str, qty: int) -> InlineKeyboardMarkup:
    qty = max(1, int(qty or 1))
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➖", callback_data=f"qty:minus:{ctx}"),
            InlineKeyboardButton(text=str(qty), callback_data="noop"),
            InlineKeyboardButton(text="➕", callback_data=f"qty:plus:{ctx}"),
        ],
        [
            InlineKeyboardButton(text="✅ Готово", callback_data=f"qty:ok:{ctx}"),
            InlineKeyboardButton(text="⬅ Назад", callback_data=f"qty:back:{ctx}"),
        ],
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