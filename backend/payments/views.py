import json
import time
import hmac
import hashlib
import requests
import httpx
from django.conf import settings
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt

from .models import Payment


def _hmac_md5(secret: str, s: str) -> str:
    return hmac.new(secret.encode("utf-8"), s.encode("utf-8"), hashlib.md5).hexdigest()


def payment_success_kb() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "📦 Мої замовлення", "callback_data": "orders:list"}],
            [{"text": "❌ Скасувати замовлення", "callback_data": "order:cancel"}],
        ]
    }


def send_telegram_message(chat_id: int, text: str, reply_markup: dict | None = None):
    url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage"

    if not getattr(settings, "BOT_TOKEN", ""):
        print("❌ BOT_TOKEN is empty in Django settings")
        return

    payload = {"chat_id": int(chat_id), "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            print("❌ Telegram API error:", r.status_code, r.text)
        else:
            # можна прибрати, але для дебагу корисно
            print("✅ Telegram sent:", r.text)
    except Exception as e:
        print("Telegram send error:", e)


def _verify_callback_signature(data: dict) -> bool:
    # merchantAccount;orderReference;amount;currency;authCode;cardPan;transactionStatus;reasonCode
    sign_string = ";".join([
        str(data.get("merchantAccount", "")),
        str(data.get("orderReference", "")),
        str(data.get("amount", "")),
        str(data.get("currency", "")),
        str(data.get("authCode", "")),
        str(data.get("cardPan", "")),
        str(data.get("transactionStatus", "")),
        str(data.get("reasonCode", "")),
    ])
    expected = _hmac_md5(settings.WFP_SECRET_KEY, sign_string)
    return expected == str(data.get("merchantSignature", ""))


def _build_accept(order_reference: str) -> dict:
    ts = int(time.time())
    status = "accept"
    signature = _hmac_md5(settings.WFP_SECRET_KEY, f"{order_reference};{status};{ts}")
    return {"orderReference": order_reference, "status": status, "time": ts, "signature": signature}


@csrf_exempt
def wayforpay_callback(request):
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    order_ref = str(data.get("orderReference", "")).strip()
    if not order_ref:
        return HttpResponseBadRequest("Missing orderReference")

    if not _verify_callback_signature(data):
        return HttpResponseBadRequest("Invalid signature")

    tx_status = str(data.get("transactionStatus", "")).lower()

    pay = Payment.objects.select_related("order").filter(order_reference=order_ref).first()
    if pay:
        pay.transaction_status = str(data.get("transactionStatus", ""))
        pay.reason_code = str(data.get("reasonCode", ""))
        pay.raw_callback = data

        # беремо chat_id З Payment (бо в Order його немає)
        chat_id = getattr(pay, "telegram_id", None)

        # ✅ Успішна оплата
        if tx_status in ("approved", "success"):
            was_paid = (pay.status == Payment.Status.PAID)

            pay.status = Payment.Status.PAID

            # якщо є notified — відмічаємо, щоб не дублювати
            can_notify = hasattr(pay, "notified")
            already_notified = getattr(pay, "notified", False)

            if can_notify and not was_paid and chat_id and not already_notified:
                # якщо ти не знаєш реальний is_subscribed — постав True або витягни з order/профілю
                kb = payment_success_kb(True)
                send_telegram_message(
                    chat_id,
                    "✅ Ваше замовлення успішно оплачено!\n"
                    "Очікуйте кур'єра 13:00–14:00 🚚",
                    reply_markup=payment_success_kb()
                )
                pay.notified = True

            elif (not can_notify) and (not was_paid) and chat_id:
                # якщо поля notified ще нема — просто шлем 1 раз по was_paid
                kb = payment_success_kb(True)
                send_telegram_message(
                    chat_id,
                    "✅ Ваше замовлення успішно оплачено!\n"
                    "Очікуйте кур'єра 13:00–14:00 🚚",
                    reply_markup=payment_success_kb()
                )

        # ❌ Неуспішна
        elif tx_status in ("declined", "failed"):
            was_failed = (pay.status == Payment.Status.FAILED)
            pay.status = Payment.Status.FAILED

            if not was_failed and chat_id:
                send_telegram_message(chat_id, f"❌ Оплата не пройшла.\nЗамовлення №{pay.order_id}")

        # save (update_fields тільки існуючі)
        fields = ["status", "transaction_status", "reason_code", "raw_callback", "updated_at"]
        if hasattr(pay, "notified"):
            fields.append("notified")
        pay.save(update_fields=fields)

    return JsonResponse(_build_accept(order_ref))


async def refund_payment(*, order_reference: str, amount: str, currency: str = "UAH",
                         comment: str = "Cancel order") -> dict:
    merchant_account = str(settings.WFP_MERCHANT_ACCOUNT).strip()
    secret = str(settings.WFP_SECRET_KEY).strip()

    # Підпис для REFUND: merchantAccount;orderReference;amount;currency
    sign_string = ";".join([merchant_account, str(order_reference), str(amount), str(currency)])
    signature = _hmac_md5(secret, sign_string)

    payload = {
        "apiVersion": 1,
        "transactionType": "REFUND",
        "merchantAccount": merchant_account,
        "orderReference": str(order_reference),
        "amount": str(amount),
        "currency": currency,
        "comment": comment,
        "merchantSignature": signature,
    }

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post("https://api.wayforpay.com/api", json=payload)
        return r.json()
