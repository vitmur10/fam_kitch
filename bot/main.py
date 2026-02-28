import asyncio
import os
import sys
from pathlib import Path

# ----------------------------------
# Django setup
# ----------------------------------

# E:\Проекти\fam_kitch\backend
BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend"

# Додаємо backend/ у sys.path
sys.path.insert(0, str(BACKEND_ROOT))

# settings.py лежить у backend/backend/settings.py
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")

import django
django.setup()

# ----------------------------------
# Aiogram
# ----------------------------------

from aiogram import Bot, Dispatcher
from bot.config import BOT_TOKEN
from bot.commands import router


async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())