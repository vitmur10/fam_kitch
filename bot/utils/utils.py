import time
from datetime import date as dt_date
from typing import Any
from django.db import models, transaction
from asgiref.sync import sync_to_async
from django.apps import apps
from decimal import Decimal
from django.conf import settings
_cache: dict[str, tuple[float, dict[str, Any]]] = {}  # key -> (expires_at, data)


def _parse_mode(v: str | None):
    if not v:
        return None
    v = v.lower()
    if v == "none":
        return None
    return v.upper()  # HTML / MARKDOWN


def _parse_date(date_str: str | None) -> dt_date | None:
    if not date_str:
        return None
    try:
        y, m, d = map(int, date_str.split("-"))
        return dt_date(y, m, d)
    except Exception:
        return None


@sync_to_async
def _get_bot_message_from_db(key: str) -> dict[str, Any] | None:
    """ORM-версія отримання повідомлення з БД"""
    BotMessage = apps.get_model("message", "BotMessage")
    obj = (
        BotMessage.objects
        .filter(key=key, is_active=True)
        .only("text", "parse_mode")
        .first()
    )
    if not obj:
        return None
    return {"text": obj.text, "parse_mode": obj.parse_mode}


async def get_bot_text(key: str, ttl: int = 300):
    """Поведінка не змінена: кеш + {text, parse_mode}. Тільки джерело — ORM."""
    now = time.time()
    cached = _cache.get(key)
    if cached and cached[0] > now:
        return cached[1]

    data = await _get_bot_message_from_db(key)
    if not data:
        data = {"text": f"[Missing message: {key}]", "parse_mode": "HTML"}

    data["parse_mode"] = _parse_mode(data.get("parse_mode"))
    _cache[key] = (now + ttl, data)
    return data


@sync_to_async
def _get_active_menu_from_db(date: str | None = None):
    MenuDay = apps.get_model("menu", "MenuDay")
    MenuItem = apps.get_model("menu", "MenuItem")

    target_date = _parse_date(date)

    qs = MenuDay.objects.filter(is_active=True)
    day = qs.filter(date=target_date).first() if target_date else qs.order_by("-date").first()

    if not day:
        return None, None, [], None

    items_out: list[dict[str, Any]] = []

    for it in MenuItem.objects.filter(menu_day=day, is_active=True).order_by("sort_order", "id"):
        item_title = getattr(it, "title", "") or ""
        positions_out: list[dict[str, Any]] = []

        def add_pos(key: str, title: str, price: int):
            title = (title or "").strip()
            if price and title:
                positions_out.append({"key": key, "title": title, "price": int(price)})

        add_pos(f"full:{it.id}", getattr(it, "full_title", "Комплекс повністю"), int(getattr(it, "full_price", 0) or 0))
        add_pos(f"p1:{it.id}", getattr(it, "first_title", "Перша страва"), int(getattr(it, "first_price", 0) or 0))
        add_pos(f"p2:{it.id}", getattr(it, "second_title", "Друга страва"), int(getattr(it, "second_price", 0) or 0))

        third_title = getattr(it, "third_title", "") or ""
        third_price = int(getattr(it, "third_price", 0) or 0)
        if third_title.strip() and third_price > 0:
            add_pos(f"p3:{it.id}", third_title, third_price)

        items_out.append({"id": it.id, "title": item_title, "positions": positions_out})

    image_data = None
    if getattr(day, "image", None):
        media_base_url = getattr(settings, "MEDIA_BASE_URL", "").rstrip("/")
        image_data = {
            "path": day.image.path,
            "url": f"{media_base_url}{day.image.url}" if media_base_url else day.image.url,
        }

    return day.id, day.date.isoformat(), items_out, image_data


async def get_menu(date: str | None = None):
    day_id, day_date, items, image_data = await _get_active_menu_from_db(date)
    return day_id, day_date, items, image_data


def render_menu_text(date: str, items: list[dict]) -> str:
    lines = [f"📅 <b>Меню на тиждень</b>\n{date}\n"]
    for it in items:
        lines.append(f"<b>{it['title']} — {it.get('price','')}₴</b>")
    return "\n".join(lines)


# ===================== ЗБЕРЕЖЕННЯ В БАЗУ (ORM) =====================



@sync_to_async
def orm_create_order(payload: dict) -> dict | None:
    """
    ORM create order WITHOUT MenuPosition.

    payload:
      - telegram_id
      - location_code
      - menu_day_id
      - cart: {"full:<item_id>": qty, "p1:<item_id>": qty, ...}
      - phone/first_name/username/comment (optional)
    """
    MenuDay = apps.get_model("menu", "MenuDay")
    MenuItem = apps.get_model("menu", "MenuItem")

    Order = apps.get_model("orders", "Order")
    CustomerModel = apps.get_model("orders", "Customer")
    LocationModel = apps.get_model("orders", "DeliveryLocation")

    # find line model name safely
    Line = None
    for name in ("OrderLine", "OrderItem", "OrderPosition"):
        try:
            Line = apps.get_model("orders", name)
            break
        except Exception:
            continue

    def _item_positions_map(item: MenuItem) -> dict[str, dict]:
        m: dict[str, dict] = {}

        def put(k: str, title: str, price: int):
            title = (title or "").strip()
            if title and int(price or 0) > 0:
                m[k] = {"title": title, "price": int(price)}

        put(f"full:{item.id}", getattr(item, "full_title", "Комплекс повністю"), int(getattr(item, "full_price", 0) or 0))
        put(f"p1:{item.id}", getattr(item, "first_title", "Перша страва"), int(getattr(item, "first_price", 0) or 0))
        put(f"p2:{item.id}", getattr(item, "second_title", "Друга страва"), int(getattr(item, "second_price", 0) or 0))

        third_title = getattr(item, "third_title", "") or ""
        third_price = int(getattr(item, "third_price", 0) or 0)
        if third_title.strip() and third_price > 0:
            put(f"p3:{item.id}", third_title, third_price)

        return m

    def _get_or_create_location(code: str):
        code = (code or "").strip()
        if not code:
            return None

        fields = {ff.name for ff in LocationModel._meta.get_fields() if isinstance(ff, models.Field)}

        # try find
        if "code" in fields:
            obj = LocationModel.objects.filter(code=code).first()
            if obj:
                return obj

        # create minimal
        create_kwargs = {}
        if "code" in fields:
            create_kwargs["code"] = code
        if "title" in fields:
            create_kwargs["title"] = code
        if "name" in fields:
            create_kwargs["name"] = code

        return LocationModel.objects.create(**create_kwargs) if create_kwargs else None

    # --- validate day
    menu_day_id = int(payload.get("menu_day_id") or 0)
    day = MenuDay.objects.filter(id=menu_day_id).first()
    if not day:
        raise RuntimeError(f"MenuDay id={menu_day_id} not found")

    # --- build key_map for that day
    items = list(MenuItem.objects.filter(menu_day=day, is_active=True).order_by("sort_order", "id"))
    key_map: dict[str, dict] = {}
    for it in items:
        key_map.update(_item_positions_map(it))

    cart = payload.get("cart") or {}
    if not isinstance(cart, dict) or not cart:
        raise RuntimeError("Cart is empty")

    missing = [k for k in cart.keys() if k not in key_map]
    if missing:
        raise RuntimeError(f"Invalid cart keys for this day: {missing}")

    # subtotal
    subtotal_int = 0
    for k, qty in cart.items():
        qty = int(qty)
        price = int(key_map[k]["price"])
        subtotal_int += price * qty

    telegram_id = int(payload.get("telegram_id") or 0)
    if telegram_id <= 0:
        raise RuntimeError("telegram_id is required")

    phone = payload.get("phone") or ""
    first_name = payload.get("first_name") or ""
    username = payload.get("username") or ""
    location_code = payload.get("location_code") or payload.get("location") or ""
    comment = payload.get("comment") or ""

    # customer create/update
    cust_fields = {f.name for f in CustomerModel._meta.get_fields() if isinstance(f, models.Field)}
    defaults = {}
    if "phone" in cust_fields:
        defaults["phone"] = phone
    if "first_name" in cust_fields:
        defaults["first_name"] = first_name
    if "username" in cust_fields:
        defaults["username"] = username

    customer, _ = CustomerModel.objects.get_or_create(telegram_id=telegram_id, defaults=defaults)

    upd = []
    for k, v in (("phone", phone), ("first_name", first_name), ("username", username)):
        if k in cust_fields and v and getattr(customer, k, None) != v:
            setattr(customer, k, v)
            upd.append(k)
    if upd:
        customer.save(update_fields=upd)

    loc = _get_or_create_location(str(location_code))
    if loc is None:
        raise RuntimeError(f"Location not found for '{location_code}' and cannot be created")

    subtotal = Decimal(subtotal_int)

    with transaction.atomic():
        # create order first with safe totals
        order_kwargs = {
            "customer": customer,
            "location": loc,
            "menu_day": day,
            "comment": comment,
        }

        order_fields = {f.name for f in Order._meta.get_fields() if isinstance(f, models.Field)}

        # totals fields (optional)
        if "subtotal" in order_fields:
            order_kwargs["subtotal"] = subtotal
        if "total" in order_fields:
            order_kwargs["total"] = subtotal
        # delivery_fee якщо є — лишимо default (0), потім перерахуємо

        order = Order.objects.create(**order_kwargs)

        # create lines
        if Line:
            line_fields = {f.name for f in Line._meta.get_fields() if isinstance(f, models.Field)}

            for key, qty in cart.items():
                meta = key_map[key]
                title = meta["title"]
                price = Decimal(int(meta["price"]))
                qty = int(qty)
                line_total = price * qty

                kw = {
                    "order": order,
                    "title_snapshot": title,
                    "price_snapshot": price,
                    "qty": qty,
                    "line_total": line_total,
                }

                if "item_key_snapshot" in line_fields:
                    kw["item_key_snapshot"] = key

                # auto-fill any remaining NOT NULL non-FK fields
                for f in Line._meta.get_fields():
                    if not isinstance(f, models.Field):
                        continue
                    if f.primary_key or f.auto_created:
                        continue
                    if f.name in kw:
                        continue
                    if f.null or f.has_default():
                        continue

                    lname = f.name.lower()
                    if isinstance(f, (models.CharField, models.TextField)):
                        kw[f.name] = ""
                    elif isinstance(f, (models.IntegerField, models.PositiveIntegerField)):
                        kw[f.name] = 0
                    elif isinstance(f, models.DecimalField):
                        kw[f.name] = Decimal("0")
                    elif isinstance(f, models.BooleanField):
                        kw[f.name] = False
                    elif isinstance(f, models.ForeignKey):
                        raise RuntimeError(f"OrderLine required FK '{f.name}' is NOT NULL; make it nullable or fill explicitly")
                    else:
                        raise RuntimeError(f"OrderLine required field '{f.name}' is NOT NULL; cannot auto-fill")

                Line.objects.create(**kw)

        # recompute total if delivery_fee exists
        if "delivery_fee" in order_fields and "total" in order_fields:
            df = getattr(order, "delivery_fee", Decimal("0")) or Decimal("0")
            order.total = (getattr(order, "subtotal", subtotal) or subtotal) + Decimal(df)
            order.save(update_fields=["total"])

    return {"id": order.id, "total": str(getattr(order, "total", subtotal))}


@sync_to_async
def orm_set_subscribe(payload: dict) -> dict | None:
    """ORM-еквівалент підписки в БД."""

    Customer = None
    for name in ("Customer", "Client", "User"):
        try:
            Customer = apps.get_model("orders", name)
            break
        except Exception:
            pass

    if Customer is None:
        return {"ok": True}

    telegram_id = int(payload.get("telegram_id"))
    is_sub = bool(payload.get("is_subscribed"))

    fields = {f.name for f in Customer._meta.get_fields()}
    defaults = {}
    if "is_subscribed" in fields:
        defaults["is_subscribed"] = is_sub

    obj, _ = Customer.objects.get_or_create(telegram_id=telegram_id, defaults=defaults)

    if "is_subscribed" in fields and getattr(obj, "is_subscribed", None) != is_sub:
        obj.is_subscribed = is_sub
        obj.save(update_fields=["is_subscribed"])

    return {"ok": True}

# ===================== CUSTOMER HELPERS =====================

@sync_to_async
def orm_get_customer_phone(telegram_id: int) -> str:
    Customer = apps.get_model("orders", "Customer")
    obj = Customer.objects.filter(telegram_id=int(telegram_id)).only("phone").first()
    return (obj.phone or "").strip() if obj else ""


@sync_to_async
def orm_set_customer_phone(telegram_id: int, phone: str, first_name: str = "", username: str = "") -> bool:
    Customer = apps.get_model("orders", "Customer")
    telegram_id = int(telegram_id)
    phone = (phone or "").strip()
    if not phone:
        return False

    obj, _ = Customer.objects.get_or_create(
        telegram_id=telegram_id,
        defaults={"phone": phone, "first_name": first_name or "", "username": username or ""},
    )

    upd = []
    if (obj.phone or "").strip() != phone:
        obj.phone = phone
        upd.append("phone")
    if first_name and (obj.first_name or "") != first_name:
        obj.first_name = first_name
        upd.append("first_name")
    if username and (obj.username or "") != username:
        obj.username = username
        upd.append("username")

    if upd:
        obj.save(update_fields=upd)

    return True


@sync_to_async
def orm_get_customer_location(telegram_id: int) -> str:
    Customer = apps.get_model("orders", "Customer")
    obj = Customer.objects.filter(telegram_id=int(telegram_id)).only("location_code").first()
    return (getattr(obj, "location_code", "") or "").strip() if obj else ""


@sync_to_async
def orm_set_customer_location(telegram_id: int, location_code: str) -> bool:
    Customer = apps.get_model("orders", "Customer")
    telegram_id = int(telegram_id)
    location_code = (location_code or "").strip()
    if not location_code:
        return False

    obj, _ = Customer.objects.get_or_create(telegram_id=telegram_id, defaults={"location_code": location_code})

    if (getattr(obj, "location_code", "") or "").strip() != location_code:
        obj.location_code = location_code
        obj.save(update_fields=["location_code"])

    return True


# ===================== ORDER HELPERS =====================

@sync_to_async
def orm_get_active_order_for_day(telegram_id: int, menu_day_id: int) -> dict | None:
    """Returns last non-cancelled order for this customer & menu_day."""
    Order = apps.get_model("orders", "Order")
    Customer = apps.get_model("orders", "Customer")

    customer = Customer.objects.filter(telegram_id=int(telegram_id)).first()
    if not customer:
        return None

    qs = (
        Order.objects
        .filter(customer=customer, menu_day_id=int(menu_day_id))
        .exclude(status=getattr(Order, "Status").CANCELLED)
        .order_by("-id")
    )
    o = qs.first()
    if not o:
        return None
    return {"id": o.id, "status": o.status, "created_at": o.created_at}


@sync_to_async
def orm_cancel_order(telegram_id: int, order_id: int) -> bool:
    """Cancels order if it belongs to user and is not DONE/CANCELLED."""
    Order = apps.get_model("orders", "Order")
    Customer = apps.get_model("orders", "Customer")

    customer = Customer.objects.filter(telegram_id=int(telegram_id)).first()
    if not customer:
        return False

    o = Order.objects.filter(id=int(order_id), customer=customer).first()
    if not o:
        return False

    st = (o.status or "").lower()
    if st in ("done", "cancelled"):
        return False

    # set cancelled
    cancelled_val = getattr(Order, "Status").CANCELLED if hasattr(Order, "Status") else "cancelled"
    o.status = cancelled_val
    o.save(update_fields=["status"])
    return True
