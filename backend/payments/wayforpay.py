import time
import hmac
import hashlib
import httpx
from django.conf import settings

WFP_API = "https://api.wayforpay.com/api"


def _hmac_md5(secret: str, s: str) -> str:
    return hmac.new(secret.encode("utf-8"), s.encode("utf-8"), hashlib.md5).hexdigest()


def _as_int_str(x) -> str:
    """
    WayForPay дуже чутливий до форматів.
    Робимо суми/ціни як рядки цілих (для UAH).
    """
    return str(int(float(x)))


async def create_invoice(*, order_reference: str, amount: int, products: list[dict]) -> dict:
    merchant_account = str(getattr(settings, "WFP_MERCHANT_ACCOUNT", "") or "").strip()
    secret = str(getattr(settings, "WFP_SECRET_KEY", "") or "").strip()
    domain = str(getattr(settings, "WFP_MERCHANT_DOMAIN", "") or "").strip()
    service_url = str(getattr(settings, "WFP_SERVICE_URL", "") or "").strip()

    if len(merchant_account) < 6:
        raise ValueError("WFP_MERCHANT_ACCOUNT is empty/invalid")
    if not secret:
        raise ValueError("WFP_SECRET_KEY is empty/invalid")
    if not domain:
        raise ValueError("WFP_MERCHANT_DOMAIN is empty/invalid")

    currency = "UAH"
    order_date = int(time.time())

    # 1) нормалізуємо товари
    product_names = [str(p["name"]) for p in products]
    product_counts = [str(int(p["count"])) for p in products]
    product_prices = [_as_int_str(p["price"]) for p in products]

    # 2) amount має дорівнювати сумі товарів — і тим же форматом
    calc_amount = sum(int(c) * int(pr) for c, pr in zip(product_counts, product_prices))
    amount_str = _as_int_str(calc_amount)

    # 3) ПІДПИС: merchantAccount;merchantDomainName;orderReference;orderDate;amount;currency;
    #            productName...;productCount...;productPrice...
    sign_parts = [
        merchant_account,
        domain,
        str(order_reference),
        str(order_date),
        amount_str,
        currency,
        *product_names,
        *product_counts,
        *product_prices,
    ]
    sign_string = ";".join(sign_parts)
    signature = _hmac_md5(secret, sign_string)

    # 4) PAYLOAD — формати мають відповідати sign_string
    payload = {
        "apiVersion": 1,
        "transactionType": "CREATE_INVOICE",
        "merchantAccount": merchant_account,
        "merchantDomainName": domain,
        "orderReference": str(order_reference),
        "orderDate": order_date,
        "amount": amount_str,                 # ← рядок!
        "currency": currency,
        "productName": product_names,
        "productCount": [int(x) for x in product_counts],
        "productPrice": [int(x) for x in product_prices],
        "serviceUrl": service_url,
        "merchantSignature": signature,
    }

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(WFP_API, json=payload)
        return r.json()