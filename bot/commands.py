from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest
import traceback
from datetime import datetime
from zoneinfo import ZoneInfo
import time
from asgiref.sync import sync_to_async
from django.apps import apps
# from payments.wayforpay import create_invoice
# from payments.views import refund_payment
from keyboards.main import main_menu_kb, menu_kb, after_confirm_kb
from keyboards.locations import locations_kb
from keyboards.qty_picker import qty_kb
from utils.utils import (
    get_bot_text, get_menu,
    orm_create_order, orm_set_subscribe,
    orm_get_customer_phone, orm_set_customer_phone,
    orm_get_customer_location, orm_set_customer_location,
    orm_get_active_order_for_day, orm_cancel_order,
)
from aiogram.fsm.state import State, StatesGroup
import os
from aiogram.types import FSInputFile
import uuid
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import GROUP_CHAT_ID

router = Router()


# ================= helpers =================

KYIV_TZ = ZoneInfo("Europe/Kyiv")


class PaymentProofState(StatesGroup):
    waiting_for_screenshot = State()
    waiting_for_refund_details = State()


def _now_kyiv() -> datetime:
    return datetime.now(tz=KYIV_TZ)


def _is_working_hours_kyiv(dt: datetime) -> bool:
    h = dt.hour
    # 12:00-19:00 and 06:00-09:00
    return (12 <= h < 19) or (6 <= h < 9)


def _display_name(user) -> str:
    if getattr(user, "username", None):
        return "@" + user.username
    return (getattr(user, "first_name", "") or "").strip() or "друже"


def _is_private_message(message: Message) -> bool:
    return getattr(message.chat, "type", "") == "private"


def _is_private_callback(cb: CallbackQuery) -> bool:
    return bool(cb.message and getattr(cb.message.chat, "type", "") == "private")


def _is_group_callback(cb: CallbackQuery) -> bool:
    return bool(cb.message and cb.message.chat.id == GROUP_CHAT_ID)


def cancel_state_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Скасувати", callback_data="state:cancel")]
        ]
    )


def refund_request_kb(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💸 Подати заявку на повернення", callback_data=f"payment:refund:{order_id}")]
        ]
    )


async def send_menu_message(target, text: str, items: list[dict], frozen_items: list[dict], menu_image: dict | None):
    if menu_image:
        image_url = (menu_image.get("url") or "").strip()
        image_path = (menu_image.get("path") or "").strip()

        if image_url.startswith("http://") or image_url.startswith("https://"):
            await target.answer_photo(
                photo=image_url,
                caption=text,
                reply_markup=menu_kb(items, frozen_items, cart={})
            )
            return

        if image_path and os.path.exists(image_path):
            await target.answer_photo(
                photo=FSInputFile(image_path),
                caption=text,
                reply_markup=menu_kb(items, frozen_items, cart={})
            )
            return

    await target.answer(text, reply_markup=menu_kb(items, frozen_items, cart={}))

async def safe_edit_kb(cb: CallbackQuery, reply_markup, fallback_text: str | None = None):
    """
    1) пробуємо edit_reply_markup
    2) якщо не вийшло — надсилаємо нове повідомлення з клавіатурою
    """
    try:
        await cb.message.edit_reply_markup(reply_markup=reply_markup)
    except TelegramBadRequest as e:
        msg = str(e).lower()
        if "message is not modified" in msg:
            return
        if fallback_text is None:
            fallback_text = "Оновив клавіатуру 👇"
        await cb.message.answer(fallback_text, reply_markup=reply_markup)


def _positions_map(items: list[dict], frozen_items: list[dict]) -> dict:
    m = {}

    for it in items or []:
        for p in it.get("positions", []) or []:
            key = p.get("key")
            if key:
                m[str(key)] = {"title": p.get("title", ""), "price": int(p.get("price") or 0)}

    for fr in frozen_items or []:
        p = fr.get("position") or {}
        key = p.get("key")
        if key:
            m[str(key)] = {"title": p.get("title", ""), "price": int(p.get("price") or 0)}

    return m


def _cart_to_lines(cart: dict, items: list[dict], frozen_items: list[dict]) -> tuple[list[str], int]:
    pm = _positions_map(items, frozen_items)
    lines = []
    total = 0
    for key, qty in (cart or {}).items():
        meta = pm.get(str(key))
        if not meta:
            continue
        qty = int(qty)
        price = int(meta["price"])
        line_total = price * qty
        total += line_total
        lines.append(f"• {meta['title']} — {qty} шт. ({line_total}₴)")
    return lines, total


# ================= START =================

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    if not _is_private_message(message):
        return

    await state.clear()
    await state.update_data(is_subscribed=True)

    # load saved customer data from DB
    db_phone = await orm_get_customer_phone(message.from_user.id)
    if db_phone:
        await state.update_data(phone=db_phone)

    db_loc = await orm_get_customer_location(message.from_user.id)
    if db_loc:
        await state.update_data(location=db_loc)

    msg = await get_bot_text("welcome")
    name = _display_name(message.from_user)

    await message.answer(
        f"👋 {name}\n\n{msg['text']}",
        parse_mode=msg.get("parse_mode"),
        reply_markup=main_menu_kb(has_phone=bool(db_phone), show_order=True)
    )


@router.message(F.contact)
async def on_contact(message: Message, state: FSMContext):
    if not _is_private_message(message):
        return

    phone = (message.contact.phone_number or "").strip()

    await orm_set_customer_phone(
        telegram_id=message.from_user.id,
        phone=phone,
        first_name=message.from_user.first_name or "",
        username=message.from_user.username or "",
    )

    await state.update_data(phone=phone)

    msg = await get_bot_text("phone_saved")
    await message.answer(
        msg["text"],
        parse_mode=msg.get("parse_mode"),
        reply_markup=main_menu_kb(has_phone=True, show_order=True)
    )


@router.message(F.text == "🥗 Замовити")
async def on_order(message: Message, state: FSMContext):
    if not _is_private_message(message):
        return

    data = await state.get_data()

    phone = (data.get("phone") or "").strip()
    if not phone:
        db_phone = await orm_get_customer_phone(message.from_user.id)
        if db_phone:
            phone = db_phone
            await state.update_data(phone=phone)

    if not phone:
        msg = await get_bot_text("ask_phone")
        await message.answer(
            msg["text"],
            parse_mode=msg.get("parse_mode"),
            reply_markup=main_menu_kb(has_phone=False, show_order=True)
        )
        return

    loc = (data.get("location") or "").strip()
    if not loc:
        db_loc = await orm_get_customer_location(message.from_user.id)
        if db_loc:
            loc = db_loc
            await state.update_data(location=loc)

    if not loc:
        msg = await get_bot_text("ask_location")
        await message.answer(
            msg["text"],
            parse_mode=msg.get("parse_mode"),
            reply_markup=locations_kb()
        )
        return

    await state.update_data(cart={})

    menu_day_id, menu_date, items, frozen_items, menu_image = await get_menu()
    await state.update_data(
        menu_items=items,
        frozen_items=frozen_items,
        menu_date=menu_date,
        menu_day_id=menu_day_id,
        menu_image=menu_image,
    )

    existing = await orm_get_active_order_for_day(message.from_user.id, int(menu_day_id or 0))
    if existing:
        is_subscribed = bool(data.get("is_subscribed", True))
        await message.answer(
            "✅ Ви вже зробили замовлення на сьогодні. Хочете замовити ще?",
            reply_markup=after_confirm_kb(is_subscribed)
        )
        return

    text = f"📅 Меню на {menu_date}\nОберіть позиції (можна повний комплекс, окремі страви або заморожені продукти):"
    try:
        await message.answer("Ок 👌", reply_markup=ReplyKeyboardRemove())
    except Exception:
        pass

    await send_menu_message(message, text, items, frozen_items, menu_image)


# ================= LOCATION -> MENU =================

@router.callback_query(F.data.startswith("loc:"))
async def on_location(cb: CallbackQuery, state: FSMContext):
    if not _is_private_callback(cb):
        await cb.answer()
        return

    loc = cb.data.split(":", 1)[1]

    try:
        await orm_set_customer_location(cb.from_user.id, loc)
    except Exception:
        pass

    await state.update_data(location=loc, cart={})
    await cb.answer(f"Локація: {loc} ✅")

    menu_day_id, menu_date, items, frozen_items, menu_image = await get_menu()
    await state.update_data(
        menu_items=items,
        frozen_items=frozen_items,
        menu_date=menu_date,
        menu_day_id=menu_day_id,
        menu_image=menu_image,
    )

    text = f"📅 Меню на {menu_date}\nОберіть позиції (можна повний комплекс, окремі страви або заморожені продукти):"

    try:
        await cb.message.answer("Ок 👌", reply_markup=ReplyKeyboardRemove())
    except Exception:
        pass

    await send_menu_message(cb.message, text, items, frozen_items, menu_image)


# ================= PICK POSITION =================

@router.callback_query(F.data.startswith("pick:"))
async def on_pick(cb: CallbackQuery, state: FSMContext):
    if not _is_private_callback(cb):
        await cb.answer()
        return

    key = cb.data.split(":", 1)[1]
    data = await state.get_data()
    cart = data.get("cart", {}) or {}

    current_qty = int(cart.get(key, 0) or 0)
    qty = current_qty if current_qty > 0 else 1

    await state.update_data(pending_key=key)
    await safe_edit_kb(cb, qty_kb(key, qty), "Вкажіть кількість 👇")
    await cb.answer("Вкажіть кількість 👇")


# ================= QTY Picker =================

@router.callback_query(F.data.startswith("qty:"))
async def on_qty(cb: CallbackQuery, state: FSMContext):
    if not _is_private_callback(cb):
        await cb.answer()
        return

    _, action, ctx = cb.data.split(":", 2)
    key = ctx

    data = await state.get_data()
    items = data.get("menu_items", []) or []
    frozen_items = data.get("frozen_items", []) or []
    cart = data.get("cart", {}) or {}

    qty = int(cart.get(key, 0) or 1)

    if action == "plus":
        qty += 1

    elif action == "minus":
        qty = max(1, qty - 1)

    elif action == "back":
        await safe_edit_kb(cb, menu_kb(items, frozen_items, cart=cart), "Повернув меню 👇")
        await cb.answer()
        return

    elif action == "ok":
        cart[key] = qty
        await state.update_data(cart=cart)
        await safe_edit_kb(cb, menu_kb(items, frozen_items, cart=cart), "Оновив меню 👇")
        await cb.answer("Збережено ✅")
        return

    cart[key] = qty
    await state.update_data(cart=cart)

    await safe_edit_kb(cb, qty_kb(key, qty))
    await cb.answer()


# ================= CONFIRM =================

@router.callback_query(F.data == "confirm")
async def on_confirm(cb: CallbackQuery, state: FSMContext):
    if not _is_private_callback(cb):
        await cb.answer()
        return

    data = await state.get_data()

    telegram_id = cb.from_user.id
    phone = data.get("phone", "")
    first_name = cb.from_user.first_name or ""
    username = cb.from_user.username or ""

    location_code = data.get("location")
    items = data.get("menu_items", []) or []
    frozen_items = data.get("frozen_items", []) or []
    menu_day_id = data.get("menu_day_id")
    cart = data.get("cart", {}) or {}

    if not cart:
        msg = await get_bot_text("empty_cart")
        await cb.answer(msg["text"], show_alert=True)
        return

    lines, local_total = _cart_to_lines(cart, items, frozen_items)
    if not lines:
        msg = await get_bot_text("empty_cart")
        await cb.answer(msg["text"], show_alert=True)
        return

    if not menu_day_id:
        await cb.answer("❗ Не знайдено menu_day_id. Перевір get_menu() / ORM.", show_alert=True)
        return

    payload = {
        "telegram_id": telegram_id,
        "phone": phone,
        "first_name": first_name,
        "username": username,
        "location_code": location_code,
        "menu_day_id": int(menu_day_id),
        "cart": {str(k): int(v) for k, v in cart.items()},
        "comment": "",
    }

    try:
        created = await orm_create_order(payload)
    except Exception as e:
        print("❌ orm_create_order ERROR:", repr(e))
        traceback.print_exc()
        created = None

    if not created or "id" not in created:
        await cb.message.answer("❌ Не вдалося зберегти замовлення в базу. Спробуйте ще раз або напишіть адміністратору.")
        await cb.answer()
        return

    order_id = int(created["id"])
    total = int(float(created.get("total", local_total)))

    Payment = apps.get_model("payments", "Payment")

    order_ref = f"{order_id}-{int(time.time())}-{uuid.uuid4().hex[:6]}"

    pay = await sync_to_async(Payment.objects.create)(
        order_id=order_id,
        provider="wayforpay",
        order_reference=order_ref,
        amount=str(total),
        currency="UAH",
        telegram_id=telegram_id,
    )

    pm = _positions_map(items, frozen_items)
    products = []
    for key, qty in (cart or {}).items():
        meta = pm.get(str(key))
        if not meta:
            continue
        products.append({
            "name": meta["title"],
            "count": int(qty),
            "price": int(meta["price"]),
        })

    if not products:
        products = [{"name": "Оплата замовлення", "count": 1, "price": total}]

    total = sum(p["count"] * p["price"] for p in products)

    if str(pay.amount) != str(total):
        pay.amount = str(total)
        await sync_to_async(pay.save)(update_fields=["amount"])

    payment_text = (
        f"✅ Замовлення №{order_id} створено\n"
        f"💰 До сплати: {total}₴\n\n"
        f"Реквізити для оплати:\n"
        f"💳 Монобанк\n"
        f"4441 1111 2222 3333\n\n"
        f"У коментарі вкажіть номер замовлення: {order_id}"
    )

    await state.update_data(waiting_payment_order_id=order_id)
    await state.set_state(PaymentProofState.waiting_for_screenshot)

    await cb.message.answer(payment_text)
    await cb.message.answer(
        f"Після оплати надішліть наступним повідомленням скріншот платежу для замовлення №{order_id}.\n"
        f"Щоб вийти з цього режиму, натисніть кнопку нижче.",
        reply_markup=cancel_state_kb()
    )
    await cb.answer()


# ================= REPEAT LAST =================

@router.callback_query(F.data == "order:repeat")
async def on_repeat(cb: CallbackQuery, state: FSMContext):
    if not _is_private_callback(cb):
        await cb.answer()
        return

    data = await state.get_data()

    """    now = _now_kyiv()
    if not _is_working_hours_kyiv(now):
        await cb.answer("⛔ Неможливо оформити замовлення в неробочі години.", show_alert=True)
        return"""
    last = data.get("last_order")

    if not last:
        await cb.answer("Немає попереднього замовлення 🙁", show_alert=True)
        return

    telegram_id = cb.from_user.id
    phone = data.get("phone", "")
    first_name = cb.from_user.first_name or ""
    username = cb.from_user.username or ""
    is_subscribed = bool(data.get("is_subscribed", True))

    payload = {
        "telegram_id": telegram_id,
        "phone": phone,
        "first_name": first_name,
        "username": username,
        "location_code": last.get("location"),
        "menu_day_id": int(last.get("menu_day_id")),
        "cart": {str(k): int(v) for k, v in (last.get("cart") or {}).items()},
        "comment": "",
    }

    try:
        created = await orm_create_order(payload)
    except Exception:
        created = None

    if not created or "id" not in created:
        await cb.message.answer("❌ Не вдалося повторити замовлення. Спробуйте пізніше.")
        await cb.answer()
        return

    order_id = created["id"]
    total = int(float(created.get("total", last.get("total", 0))))

    items = data.get("menu_items", []) or []
    lines, _ = _cart_to_lines(payload["cart"], items)

    text = (
        f"✅ Повторено! Ваше замовлення №{order_id}:\n"
        + "\n".join(lines)
        + f"\n\n📍 Локація: {payload['location_code']}\n💰 Разом: {total}₴"
        + "\n⏰ Очікуйте заказ 13:00–14:00"
    )

    await cb.message.answer(text, reply_markup=after_confirm_kb(is_subscribed, can_cancel=True))
    try:
        await cb.message.answer("🏠 Головне меню", reply_markup=main_menu_kb(has_phone=True, show_order=True))
    except Exception:
        pass
    await cb.answer()


# ================= SUBSCRIBE =================

@router.callback_query(F.data.startswith("sub:"))
async def on_subscribe_toggle(cb: CallbackQuery, state: FSMContext):
    if not _is_private_callback(cb):
        await cb.answer()
        return

    _, val = cb.data.split(":")
    is_sub = val == "on"

    await state.update_data(is_subscribed=is_sub)

    payload = {"telegram_id": cb.from_user.id, "is_subscribed": is_sub}
    try:
        await orm_set_subscribe(payload)
    except Exception:
        pass

    await cb.answer("Ок ✅")
    await safe_edit_kb(cb, after_confirm_kb(is_sub, can_cancel=True), None)


@router.message(F.text == "ℹ️ Допомога")
async def on_help(message: Message):
    if not _is_private_message(message):
        return

    msg = await get_bot_text("help")
    await message.answer(msg["text"], parse_mode=msg.get("parse_mode"))


@router.message(F.text == "📞 Поділитися номером")
async def on_share_phone(message: Message, state: FSMContext):
    if not _is_private_message(message):
        return

    data = await state.get_data()
    phone = (data.get("phone") or "").strip()
    if not phone:
        db_phone = await orm_get_customer_phone(message.from_user.id)
        if db_phone:
            phone = db_phone
            await state.update_data(phone=phone)

    if phone:
        await message.answer("✅ Ваш номер вже збережено.", reply_markup=main_menu_kb(has_phone=True, show_order=True))
        return

    msg = await get_bot_text("ask_phone")
    await message.answer(msg["text"], parse_mode=msg.get("parse_mode"), reply_markup=main_menu_kb(has_phone=False, show_order=True))


# ================= ORDER MORE / CHANGE LOCATION / ADMIN =================

@router.callback_query(F.data == "order:more")
async def on_order_more(cb: CallbackQuery, state: FSMContext):
    if not _is_private_callback(cb):
        await cb.answer()
        return

    data = await state.get_data()

    phone = (data.get("phone") or "").strip()
    if not phone:
        db_phone = await orm_get_customer_phone(cb.from_user.id)
        if db_phone:
            phone = db_phone
            await state.update_data(phone=phone)

    if not phone:
        msg = await get_bot_text("ask_phone")
        await cb.message.answer(msg["text"], parse_mode=msg.get("parse_mode"), reply_markup=main_menu_kb(has_phone=False, show_order=True))
        await cb.answer()
        return

    loc = (data.get("location") or "").strip()
    if not loc:
        db_loc = await orm_get_customer_location(cb.from_user.id)
        if db_loc:
            loc = db_loc
            await state.update_data(location=loc)

    if not loc:
        msg = await get_bot_text("ask_location")
        await cb.message.answer(msg["text"], parse_mode=msg.get("parse_mode"), reply_markup=locations_kb())
        await cb.answer()
        return

    await state.update_data(cart={})
    menu_day_id, menu_date, items, frozen_items, menu_image = await get_menu()
    await state.update_data(
        menu_items=items,
        frozen_items=frozen_items,
        menu_date=menu_date,
        menu_day_id=menu_day_id,
        menu_image=menu_image,
    )

    text = f"📅 Меню на {menu_date}\nОберіть позиції:"

    try:
        await cb.message.answer("Ок 👌", reply_markup=ReplyKeyboardRemove())
    except Exception:
        pass

    await send_menu_message(cb.message, text, items, frozen_items, menu_image)
    await cb.answer()


@router.callback_query(F.data == "change_location")
async def on_change_location(cb: CallbackQuery, state: FSMContext):
    if not _is_private_callback(cb):
        await cb.answer()
        return

    await state.update_data(cart={})
    msg = await get_bot_text("ask_location")
    await cb.message.answer(msg["text"], parse_mode=msg.get("parse_mode"), reply_markup=locations_kb())
    await cb.answer()


@router.callback_query(F.data == "admin:contact")
async def on_admin_contact(cb: CallbackQuery):
    if not _is_private_callback(cb):
        await cb.answer()
        return

    await cb.answer()
    await cb.message.answer("Напишіть адміністратору: @GRay_TG")


# ================= CANCEL ORDER =================

@router.callback_query(F.data == "order:cancel")
async def on_cancel_order(cb: CallbackQuery, state: FSMContext):
    if not _is_private_callback(cb):
        await cb.answer()
        return

    data = await state.get_data()
    last = data.get("last_order") or {}
    order_id = int(last.get("order_id") or 0)

    if not order_id:
        menu_day_id = int(data.get("menu_day_id") or 0)
        if menu_day_id:
            ex = await orm_get_active_order_for_day(cb.from_user.id, menu_day_id)
            if ex:
                order_id = int(ex["id"])

    if not order_id:
        await cb.answer("Немає замовлення для скасування 🙁", show_alert=True)
        return

    ok = await orm_cancel_order(cb.from_user.id, order_id)
    if not ok:
        await cb.answer("Не вдалося скасувати (можливо вже виконано).", show_alert=True)
        return

    await cb.message.answer(f"❌ Замовлення №{order_id} скасовано.")
    await cb.answer()


# ================= STATES =================

@router.callback_query(F.data == "state:cancel")
async def on_state_cancel(cb: CallbackQuery, state: FSMContext):
    if not _is_private_callback(cb):
        await cb.answer()
        return

    await state.clear()
    await cb.message.answer("❌ Дію скасовано.")
    await cb.answer()


@router.callback_query(F.data.startswith("payment:refund:"))
async def on_payment_refund_request(cb: CallbackQuery, state: FSMContext):
    if not _is_private_callback(cb):
        await cb.answer()
        return

    order_id = int(cb.data.split(":")[2])
    await state.update_data(waiting_refund_order_id=order_id)
    await state.set_state(PaymentProofState.waiting_for_refund_details)

    await cb.message.answer(
        f"Вкажіть, будь ласка, куди повернути кошти за замовлення №{order_id}.\n"
        f"Можете надіслати номер картки, IBAN або інші реквізити одним повідомленням.",
        reply_markup=cancel_state_kb()
    )
    await cb.answer()


# ================= GROUP MODERATION =================

@router.callback_query(F.data.startswith("proof:approve:"))
async def on_proof_approve(cb: CallbackQuery):
    if not _is_group_callback(cb):
        await cb.answer()
        return

    _, _, order_id, telegram_id = cb.data.split(":")
    order_id = int(order_id)
    telegram_id = int(telegram_id)

    try:
        await cb.bot.send_message(
            telegram_id,
            f"✅ Вашу оплату за замовленням №{order_id} підтверджено.",
            reply_markup=refund_request_kb(order_id)
        )
    except Exception:
        pass

    await cb.message.edit_caption(
        caption=(cb.message.caption or "") + "\n\n✅ Оплату підтверджено"
    )
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.answer("Оплату підтверджено")


@router.callback_query(F.data.startswith("proof:reject:"))
async def on_proof_reject(cb: CallbackQuery):
    if not _is_group_callback(cb):
        await cb.answer()
        return

    _, _, order_id, telegram_id = cb.data.split(":")
    order_id = int(order_id)
    telegram_id = int(telegram_id)

    try:
        await cb.bot.send_message(
            telegram_id,
            f"❌ Скріншот оплати за замовленням №{order_id} не підтверджено. Будь ласка, перевірте оплату або надішліть інший скрін."
        )
    except Exception:
        pass

    await cb.message.edit_caption(
        caption=(cb.message.caption or "") + "\n\n❌ Оплату не підтверджено"
    )
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.answer("Оплату відхилено")


@router.callback_query(F.data.startswith("refund:approve:"))
async def on_refund_approve(cb: CallbackQuery):
    if not _is_group_callback(cb):
        await cb.answer()
        return

    _, _, order_id, telegram_id = cb.data.split(":")
    order_id = int(order_id)
    telegram_id = int(telegram_id)

    try:
        await cb.bot.send_message(
            telegram_id,
            f"✅ Заявку на повернення коштів за замовленням №{order_id} прийнято в обробку."
        )
    except Exception:
        pass

    await cb.message.edit_caption(
        caption=(cb.message.caption or "") + "\n\n✅ Заявку на повернення прийнято"
    )
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.answer("Заявку прийнято")


@router.callback_query(F.data.startswith("refund:reject:"))
async def on_refund_reject(cb: CallbackQuery):
    if not _is_group_callback(cb):
        await cb.answer()
        return

    _, _, order_id, telegram_id = cb.data.split(":")
    order_id = int(order_id)
    telegram_id = int(telegram_id)

    try:
        await cb.bot.send_message(
            telegram_id,
            f"❌ Заявку на повернення коштів за замовленням №{order_id} відхилено. Зв’яжіться з адміністратором для уточнення."
        )
    except Exception:
        pass

    await cb.message.edit_caption(
        caption=(cb.message.caption or "") + "\n\n❌ Заявку на повернення відхилено"
    )
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.answer("Заявку відхилено")


# ================= USER MEDIA / FORMS =================

@router.message(PaymentProofState.waiting_for_screenshot, F.photo)
async def on_payment_screenshot(message: Message, state: FSMContext):
    if not _is_private_message(message):
        return

    data = await state.get_data()
    order_id = int(data.get("waiting_payment_order_id") or 0)

    if not order_id:
        await message.answer("Не вдалося визначити номер замовлення.")
        await state.clear()
        return

    user = message.from_user
    username = f"@{user.username}" if user.username else "-"
    first_name = user.first_name or "-"
    telegram_id = user.id

    caption = (
        f"📥 Новий скрін оплати\n\n"
        f"Замовлення №{order_id}\n"
        f"Користувач: {first_name}\n"
        f"Username: {username}\n"
        f"Telegram ID: {telegram_id}"
    )

    admin_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Підтвердити", callback_data=f"proof:approve:{order_id}:{telegram_id}"),
                InlineKeyboardButton(text="❌ Не підтвердити", callback_data=f"proof:reject:{order_id}:{telegram_id}"),
            ]
        ]
    )

    await message.bot.send_photo(
        chat_id=GROUP_CHAT_ID,
        photo=message.photo[-1].file_id,
        caption=caption,
        reply_markup=admin_kb
    )

    await message.answer("✅ Скріншот відправлено на перевірку адміністратору.")
    await state.clear()


@router.message(PaymentProofState.waiting_for_refund_details)
async def on_refund_details(message: Message, state: FSMContext):
    if not _is_private_message(message):
        return

    data = await state.get_data()
    order_id = int(data.get("waiting_refund_order_id") or 0)

    if not order_id:
        await message.answer("Не вдалося визначити номер замовлення для повернення.")
        await state.clear()
        return

    refund_details = (message.text or message.caption or "").strip()
    if not refund_details:
        await message.answer("Будь ласка, надішліть реквізити текстом одним повідомленням.")
        return

    user = message.from_user
    username = f"@{user.username}" if user.username else "-"
    first_name = user.first_name or "-"
    telegram_id = user.id

    caption = (
        f"💸 Нова заявка на повернення коштів\n\n"
        f"Замовлення №{order_id}\n"
        f"Користувач: {first_name}\n"
        f"Username: {username}\n"
        f"Telegram ID: {telegram_id}\n\n"
        f"Куди повернути:\n{refund_details}"
    )

    admin_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Прийняти", callback_data=f"refund:approve:{order_id}:{telegram_id}"),
                InlineKeyboardButton(text="❌ Відхилити", callback_data=f"refund:reject:{order_id}:{telegram_id}"),
            ]
        ]
    )

    await message.bot.send_message(
        chat_id=GROUP_CHAT_ID,
        text=caption,
        reply_markup=admin_kb
    )

    await message.answer("✅ Заявку на повернення відправлено адміністратору.")
    await state.clear()


@router.message(PaymentProofState.waiting_for_screenshot)
async def on_payment_screenshot_invalid(message: Message):
    if not _is_private_message(message):
        return

    await message.answer(
        "Зараз бот очікує фото скріншота оплати.\n"
        "Надішліть, будь ласка, саме фото або натисніть «❌ Скасувати»."
    )


# ================= RULE: ANY TEXT -> MENU =================

@router.message()
async def on_any_message(message: Message, state: FSMContext):
    if not _is_private_message(message):
        return

    data = await state.get_data()
    phone = (data.get("phone") or "").strip()
    if not phone:
        db_phone = await orm_get_customer_phone(message.from_user.id)
        if db_phone:
            phone = db_phone
            await state.update_data(phone=phone)

    await message.answer(
        "Оберіть один із варіантів 👇",
        reply_markup=main_menu_kb(has_phone=bool(phone), show_order=True)
    )


@router.callback_query(F.data == "orders:list")
async def my_orders(cb: CallbackQuery):
    if not _is_private_callback(cb):
        await cb.answer()
        return

    Order = apps.get_model("orders", "Order")
    Payment = apps.get_model("payments", "Payment")

    telegram_id = cb.from_user.id

    orders = await sync_to_async(list)(
        Order.objects.filter(telegram_id=telegram_id)
        .order_by("-id")[:5]
    )

    if not orders:
        await cb.message.answer("📦 У вас поки немає замовлень.")
        await cb.answer()
        return

    text = "📦 Ваші останні замовлення:\n\n"

    for order in orders:
        pay = await sync_to_async(
            Payment.objects.filter(order_id=order.id).first
        )()

        if pay and pay.status == "paid":
            status = "✅ Оплачено"
        elif pay:
            status = "💳 Очікує оплату"
        else:
            status = "⏳ Створено"

        text += f"Замовлення №{order.id}\n"
        text += f"Сума: {order.total}₴\n"
        text += f"Статус: {status}\n\n"

    await cb.message.answer(text)
    await cb.answer()


"""@router.callback_query(F.data == "order:cancel")
async def cancel_last_order(cb: CallbackQuery):
    Payment = apps.get_model("payments", "Payment")

    telegram_id = cb.from_user.id

    # останній paid-платіж цього користувача
    pay = await sync_to_async(
        Payment.objects.filter(provider="wayforpay", telegram_id=telegram_id, status=Payment.Status.PAID)
        .order_by("-id")
        .first
    )()
    if pay.status == Payment.Status.REFUNDED:
        await cb.message.answer("✅ Це замовлення вже повернуте (refund вже зроблено).")
        await cb.answer()
        return
    if not pay:
        await cb.message.answer("❗ Немає оплачених замовлень для скасування.")
        await cb.answer()
        return

    # виклик REFUND
    resp = await refund_payment(
        order_reference=pay.order_reference,
        amount=str(pay.amount),
        currency=pay.currency,
        comment="Cancel by customer in Telegram bot",
    )

    # WayForPay зазвичай повертає reasonCode=1100 для ok (може бути різне),
    # тому покажемо resp якщо не ок
    if str(resp.get("reasonCode")) in ("1100",) or str(resp.get("reason", "")).lower() == "ok":
        # помічаємо в БД
        pay.status = Payment.Status.REFUNDED
        await sync_to_async(pay.save)(update_fields=["status", "raw_callback", "updated_at"])

        await cb.message.answer(
            "✅ Замовлення скасовано.\n"
            "💸 Повернення коштів оформлено. Зазвичай надходить протягом 1–3 робочих днів."
        )
    else:
        await cb.message.answer(f"❌ Не вдалося зробити повернення.\nВідповідь WayForPay: {resp}")

    await cb.answer()"""