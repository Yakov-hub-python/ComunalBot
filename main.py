import asyncio
import os

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web

from bot import register_handlers

load_dotenv()


# ── Health check сервер для Render ──

async def health_check(request):
    """Ответ на запрос /health — Render проверяет доступность сервиса."""
    return web.json_response({"status": "ok"})


async def start_health_server():
    """Запуск HTTP-сервера на порту Render."""
    app = web.Application()
    app.router.add_get("/health", health_check)
    app.router.add_get("/", health_check)

    port = int(os.getenv("PORT", 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"✅ Health check server: http://0.0.0.0:{port}/health")
    return runner


# ── Запуск бота ──

async def main():
    bot_token = os.getenv("GET_TOKEN") or os.getenv("BOT_TOKEN")
    if not bot_token:
        raise RuntimeError("❌ Переменная окружения BOT_TOKEN не задана!")

    bot = Bot(token=bot_token)
    dp = Dispatcher(storage=MemoryStorage())

    register_handlers(dp)

    # Запуск health check сервера
    runner = await start_health_server()

    print("🤖 Бот запущен!")
    try:
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
