"""

      Telegram-бот «Личный финансовый ассистент»
      Точка входа: запуск бота и фонового планировщика

"""

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis

from config import settings
from database.db import init_db
from handlers import (
    start,
    expenses,
    income,
    budget,
    reports,
    reminders,
    voice,
    categories,
    export,
    quick,
    goals,
    patterns,
    gamification
)
from middlewares.throttling import ThrottlingMiddleware
from middlewares.user_tracker import UserTrackerMiddleware
from scheduler.tasks import setup_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


async def main() -> None:
    logger.info("🚀 Запуск бота «Личный финансовый ассистент»")

    # База данных
    await init_db()
    logger.info("✅ База данных инициализирована")
    from services.gamification import init_gamification_tables
    await init_gamification_tables()
    logger.info("✅ Таблицы геймификации инициализированы")


    # Redis (FSM storage + кэш)
    redis = Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD or None,
        decode_responses=False,
    )
    storage = RedisStorage(redis=redis)
    logger.info("✅ Redis подключён")

    #Bot & Dispatcher
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=storage)

    # Middleware
    dp.message.middleware(ThrottlingMiddleware(rate_limit=0.5))
    dp.message.middleware(UserTrackerMiddleware(redis=redis))
    dp.callback_query.middleware(UserTrackerMiddleware(redis=redis))

    # Роутеры
    dp.include_router(start.router)
    dp.include_router(voice.router)
    dp.include_router(expenses.router)
    dp.include_router(income.router)
    dp.include_router(budget.router)
    dp.include_router(reports.router)
    dp.include_router(reminders.router)
    dp.include_router(categories.router)
    dp.include_router(export.router)
    dp.include_router(quick.router)
    dp.include_router(goals.router)
    dp.include_router(patterns.router)
    dp.include_router(gamification.router)

    #  Планировщик напоминаний
    scheduler = await setup_scheduler(bot, redis)
    scheduler.start()
    logger.info("✅ Планировщик задач запущен")

    #Запуск поллинга
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("🤖 Бот начал принимать обновления...")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown(wait=False)
        await storage.close()
        await redis.aclose()
        await bot.session.close()
        logger.info("👋 Бот остановлен")


if __name__ == "__main__":
    asyncio.run(main())
