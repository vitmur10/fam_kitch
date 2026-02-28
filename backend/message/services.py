from django.core.cache import cache
from .models import BotMessage

CACHE_TIMEOUT = 60 * 5  # 5 хвилин


def get_bot_message(key: str):
    cache_key = f"bot_message_{key}"

    cached = cache.get(cache_key)
    if cached:
        return cached

    obj = (
        BotMessage.objects
        .filter(key=key, is_active=True)
        .only("text", "parse_mode")
        .first()
    )

    if not obj:
        return None

    data = {
        "text": obj.text,
        "parse_mode": obj.parse_mode,
    }

    cache.set(cache_key, data, CACHE_TIMEOUT)
    return data