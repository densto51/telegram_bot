"""
scheduler/tasks.py — APScheduler для отправки напоминаний.

Каждую минуту проверяем таблицу reminders на «просроченные» записи
и отправляем пуш-уведомления. Для повторяющихся напоминаний
пересчитываем следующую дату срабатывания.
"""

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


async def _check_and_send_reminders(bot: Bot) -> None:
    """Основная задача планировщика. Запускается каждую минуту."""
    now_str = datetime.now(TZ).strftime("%Y-%m-%dT%H:%M:%S")
    due = await get_due_reminders(until_dt=now_str)

    for r in due:
        try:
            amount_str = f"\n💰 Сумма: <b>{fmt_amount(r['amount'])}</b>" if r["amount"] else ""
            note_str = f"\n📝 {r['note']}" if r.get("note") else ""

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
            logger.info(
                "Reminder #%d sent to user %d (%s)", r["id"], r["user_id"], r["title"]
            )
        except Exception as e:
            logger.error("Failed to send reminder #%d: %s", r["id"], e)
            continue

        # ── Обновить следующую дату или деактивировать ─────────────────
        repeat = r.get("repeat_type", "none")
        if repeat == "none":
            await deactivate_reminder(r["id"])
        else:
            current_dt = datetime.fromisoformat(r["remind_at"])
            if current_dt.tzinfo is None:
                current_dt = TZ.localize(current_dt)
            next_dt = _calc_next_dt(current_dt, repeat, r.get("repeat_day"))
            await update_reminder_time(r["id"], next_dt.isoformat())


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
                # Дня не существует в следующем месяце — берём последний
                import calendar
                last_day = calendar.monthrange(next_dt.year, next_dt.month)[1]
                next_dt = next_dt.replace(day=last_day)
        return next_dt
    return dt + timedelta(days=1)


async def setup_scheduler(bot: Bot, redis: Redis) -> AsyncIOScheduler:
    """Создаёт и настраивает планировщик с хранилищем в памяти."""
    scheduler = AsyncIOScheduler(
        jobstores={"default": MemoryJobStore()},
        timezone=TZ,
    )
    scheduler.add_job(
        _check_and_send_reminders,
        trigger="interval",
        minutes=1,
        args=[bot],
        id="check_reminders",
        replace_existing=True,
        max_instances=1,
    )
    return scheduler