"""
scheduler/tasks.py — APScheduler для отправки напоминаний.

Redis используется для:
  1. FSM storage (через aiogram)
  2. Кэш отчётов (handlers/reports.py)
  3. Планировщик: хранит состояние выполненных напоминаний в Redis
     (сам APScheduler использует MemoryJobStore — Bot нельзя pickle,
      но данные о последнем запуске и статусах пишем в Redis вручную)

Каждую минуту планировщик:
  - Берёт просроченные напоминания из SQLite
  - Отправляет пуш пользователю
  - Записывает в Redis лог последней отправки
  - Пересчитывает следующую дату или деактивирует
"""

import json
import logging
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import pytz

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from aiogram import Bot
from redis.asyncio import Redis

from config import settings
from database.queries import (
    get_due_reminders,
    update_reminder_time,
    deactivate_reminder,
)
from utils.formatters import fmt_amount

logger = logging.getLogger(__name__)
TZ = pytz.timezone(settings.DEFAULT_TIMEZONE)

# Redis ключи
REDIS_REMINDER_LOG_KEY   = "reminders:last_sent:{reminder_id}"
REDIS_SCHEDULER_STATS    = "scheduler:stats"


async def _check_and_send_reminders(bot: Bot, redis: Redis) -> None:
    """Основная задача планировщика. Запускается каждую минуту."""
    now    = datetime.now(TZ)
    now_str = now.strftime("%Y-%m-%dT%H:%M:%S")

    due = await get_due_reminders(until_dt=now_str)
    if not due:
        return

    sent_count = 0

    for r in due:
        try:
            amount_str = f"\n💰 Сумма: <b>{fmt_amount(r['amount'])}</b>" if r["amount"] else ""
            note_str   = f"\n📝 {r['note']}" if r.get("note") else ""

            await bot.send_message(
                chat_id=r["user_id"],
                text=(
                    f"⏰ <b>Напоминание о платеже!</b>\n\n"
                    f"🔔 {r['title']}"
                    f"{amount_str}"
                    f"{note_str}\n\n"
                    f"<i>Зафиксировать платёж:</i> /expense"
                ),
            )

            #  Записываем в Redis лог отправки
            log_key = REDIS_REMINDER_LOG_KEY.format(reminder_id=r["id"])
            await redis.setex(
                log_key,
                86400 * 7,  # хранить 7 дней
                json.dumps({
                    "reminder_id": r["id"],
                    "user_id":     r["user_id"],
                    "title":       r["title"],
                    "sent_at":     now_str,
                }, ensure_ascii=False),
            )

            # Обновляем счётчик статистики в Redis
            await redis.hincrby(REDIS_SCHEDULER_STATS, "total_sent", 1)
            await redis.hset(REDIS_SCHEDULER_STATS, "last_run", now_str)

            sent_count += 1
            logger.info("Reminder #%d sent to user %d (%s)", r["id"], r["user_id"], r["title"])

        except Exception as e:
            logger.error("Failed to send reminder #%d: %s", r["id"], e)
            await redis.hincrby(REDIS_SCHEDULER_STATS, "total_errors", 1)
            continue

        #Обновить следующую дату или деактивировать
        repeat = r.get("repeat_type", "none")
        if repeat == "none":
            await deactivate_reminder(r["id"])
        else:
            current_dt = datetime.fromisoformat(r["remind_at"])
            if current_dt.tzinfo is None:
                current_dt = TZ.localize(current_dt)
            next_dt = _calc_next_dt(current_dt, repeat, r.get("repeat_day"))
            await update_reminder_time(r["id"], next_dt.isoformat())
            logger.info("Reminder #%d rescheduled to %s", r["id"], next_dt.isoformat())

    if sent_count:
        logger.info("Scheduler: sent %d reminder(s)", sent_count)


def _calc_next_dt(dt: datetime, repeat_type: str, repeat_day: int | None) -> datetime:
    """Вычисляет следующую дату срабатывания по типу повтора."""
    if repeat_type == "daily":
        return dt + timedelta(days=1)
    elif repeat_type == "weekly":
        return dt + timedelta(weeks=1)
    elif repeat_type == "monthly":
        next_dt = dt + relativedelta(months=1)
        if repeat_day:
            try:
                next_dt = next_dt.replace(day=repeat_day)
            except ValueError:
                import calendar
                last_day = calendar.monthrange(next_dt.year, next_dt.month)[1]
                next_dt  = next_dt.replace(day=last_day)
        return next_dt
    return dt + timedelta(days=1)


async def get_scheduler_stats(redis: Redis) -> dict:
    """Статистика планировщика из Redis (для отладки/мониторинга)."""
    stats = await redis.hgetall(REDIS_SCHEDULER_STATS)
    return {k.decode(): v.decode() for k, v in stats.items()} if stats else {}


async def setup_scheduler(bot: Bot, redis: Redis) -> AsyncIOScheduler:
    """
    Создаёт планировщик.
    APScheduler хранит джобы в памяти (MemoryJobStore) — объект Bot
    нельзя сериализовать через pickle в Redis.
    Данные о выполнении напоминаний (логи, статистика) пишем в Redis вручную.
    """
    scheduler = AsyncIOScheduler(
        jobstores={"default": MemoryJobStore()},
        timezone=TZ,
    )
    scheduler.add_job(
        _check_and_send_reminders,
        trigger="interval",
        minutes=1,
        args=[bot, redis],          # передаём redis в задачу
        id="check_reminders",
        replace_existing=True,
        max_instances=1,
    )

    # Записываем в Redis факт запуска планировщика
    await redis.hset(REDIS_SCHEDULER_STATS, "started_at", datetime.now(TZ).isoformat())
    await redis.hset(REDIS_SCHEDULER_STATS, "status", "running")

    return scheduler