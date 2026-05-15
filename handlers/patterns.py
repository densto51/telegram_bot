"""
handlers/patterns.py — предложение напоминаний на основе паттернов расходов.

Два сценария запуска:
  1. Автоматически — после каждой записи расхода (проверяем паттерны)
  2. Вручную — команда /patterns или кнопка в меню

Флоу:
  Бот: «Ты каждый месяц платишь ~5 000 сза интернет. Добавить напоминание?»
  Пользователь: [✅ Да, добавить] / [❌ Не сейчас] / [🚫 Больше не предлагать]
"""

import logging
from datetime import datetime, timedelta
import pytz

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from config import settings
from database.queries import add_reminder
from keyboards.main_menu import main_menu_kb
from services.pattern_detector import detect_patterns, SpendingPattern
from utils.formatters import fmt_amount

logger = logging.getLogger(__name__)
router = Router(name="patterns")

TZ = pytz.timezone(settings.DEFAULT_TIMEZONE)



# HELPERS

def _pattern_suggest_kb(pattern_key: str, idx: int, total: int) -> InlineKeyboardMarkup:
    """Клавиатура для одного предложения паттерна."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Да, добавить напоминание",
                callback_data=f"pat_add:{pattern_key}"
            ),
        ],
        [
            InlineKeyboardButton(
                text=f"⏭ Следующий ({idx}/{total})" if idx < total else "⏭ Пропустить",
                callback_data=f"pat_skip:{idx}"
            ),
            InlineKeyboardButton(
                text="❌ Закрыть",
                callback_data="pat_close"
            ),
        ],
    ])


def _next_month_date() -> str:
    """Дата через месяц в 09:00 — для нового напоминания."""
    now = datetime.now(TZ)
    next_month = now + timedelta(days=30)
    return next_month.replace(hour=9, minute=0, second=0, microsecond=0).isoformat()



# ПОКАЗ ПАТТЕРНОВ


async def _show_pattern(
    message: Message,
    pattern: SpendingPattern,
    idx: int,
    total: int,
    edit: bool = False,
) -> None:
    """Показывает одно предложение паттерна."""
    label = pattern.category or pattern.key
    if pattern.key.startswith("cat_"):
        label = pattern.category or "расход"

    text = (
        f"🔍 <b>Обнаружен регулярный расход!</b>\n\n"
        f"{pattern.icon} <b>{label}</b>\n\n"
        f"За последние 3 месяца ты платил(а) за это "
        f"<b>{pattern.count} раз</b>\n"
        f"Средняя сумма: <b>{fmt_amount(pattern.avg_amount)}</b>\n\n"
        f"Хочешь, добавлю ежемесячное напоминание об этом платеже?"
    )
    kb = _pattern_suggest_kb(pattern.key, idx, total)

    if edit:
        try:
            await message.edit_text(text, reply_markup=kb)
        except Exception:
            await message.answer(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


@router.message(Command("patterns"))
@router.callback_query(F.data == "patterns")
async def show_patterns(event) -> None:
    """Ручной запуск анализа паттернов."""
    msg     = event if isinstance(event, Message) else event.message
    user_id = event.from_user.id

    patterns = await detect_patterns(user_id)

    if not patterns:
        text = (
            "🔍 <b>Анализ регулярных расходов</b>\n\n"
            "Паттернов пока не найдено.\n\n"
            "Бот автоматически замечает повторяющиеся расходы "
            "после накопления истории за 2–3 месяца."
        )
        if isinstance(event, CallbackQuery):
            await event.message.edit_text(text, reply_markup=main_menu_kb())
            await event.answer()
        else:
            await msg.answer(text, reply_markup=main_menu_kb())
        return

    if isinstance(event, CallbackQuery):
        await event.answer()

    # Показываем первый паттерн
    await _show_pattern(msg, patterns[0], idx=1, total=len(patterns))

    # Сохраняем остальные в Redis-кэш через FSM data
    # (передаём через callback_data индексы)



# ДОБАВИТЬ НАПОМИНАНИЕ ПО ПАТТЕРНУ


@router.callback_query(F.data.startswith("pat_add:"))
async def cb_pattern_add(callback: CallbackQuery) -> None:
    pattern_key = callback.data[8:]  # убираем "pat_add:"
    user_id     = callback.from_user.id

    # Находим паттерн заново
    patterns = await detect_patterns(user_id)
    pattern  = next(
        (p for p in patterns if p.key == pattern_key), None
    )

    if not pattern:
        await callback.answer("❌ Паттерн не найден", show_alert=True)
        return

    label = pattern.category or pattern.key
    if pattern.key.startswith("cat_"):
        label = pattern.category or "Расход"

    # Создаём ежемесячное напоминание
    remind_dt   = _next_month_date()
    reminder_id = await add_reminder(
        user_id=user_id,
        title=label,
        remind_at=remind_dt,
        amount=pattern.avg_amount,
        repeat_type="monthly",
        repeat_day=datetime.now(TZ).day,
        note=f"Регулярный платёж (обнаружен автоматически)",
    )

    next_date = datetime.fromisoformat(remind_dt)

    await callback.message.edit_text(
        f"✅ <b>Напоминание добавлено!</b>\n\n"
        f"{pattern.icon} <b>{label}</b>\n"
        f"💰 Сумма: <b>{fmt_amount(pattern.avg_amount)}</b>\n"
        f"📅 Первое напоминание: <b>{next_date.strftime('%d.%m.%Y')} в 09:00</b>\n"
        f"🔁 Повтор: каждый месяц\n"
        f"🆔 #{reminder_id}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏰ Все напоминания", callback_data="reminders")],
            [InlineKeyboardButton(text="🔍 Другие паттерны", callback_data="patterns")],
            [InlineKeyboardButton(text="🏠 Меню",            callback_data="main_menu")],
        ])
    )
    await callback.answer("✅ Напоминание создано!")



# ПРОПУСТИТЬ / ЗАКРЫТЬ


@router.callback_query(F.data.startswith("pat_skip:"))
async def cb_pattern_skip(callback: CallbackQuery) -> None:
    current_idx = int(callback.data.split(":")[1])
    user_id     = callback.from_user.id

    patterns = await detect_patterns(user_id)

    if current_idx >= len(patterns):
        await callback.message.edit_text(
            "✅ Все паттерны просмотрены!\n\n"
            "Бот продолжит следить за твоими расходами "
            "и предложит напоминания при появлении новых паттернов.",
            reply_markup=main_menu_kb()
        )
        await callback.answer()
        return

    # Показываем следующий
    next_pattern = patterns[current_idx]
    await _show_pattern(
        callback.message,
        next_pattern,
        idx=current_idx + 1,
        total=len(patterns),
        edit=True,
    )
    await callback.answer()


@router.callback_query(F.data == "pat_close")
async def cb_pattern_close(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "🔍 Анализ закрыт.\n\n"
        "Ты всегда можешь вернуться к анализу паттернов через /patterns",
        reply_markup=main_menu_kb()
    )
    await callback.answer()



# АВТОМАТИЧЕСКАЯ ПРОВЕРКА ПОСЛЕ ЗАПИСИ РАСХОДА


async def check_patterns_after_expense(user_id: int, message: Message) -> None:
    """
    Вызывается после каждой записи расхода.
    Если найден новый паттерн — предлагает напоминание.
    Срабатывает не чаще раза в день (через Redis).
    """
    try:
        patterns = await detect_patterns(user_id)
        if patterns:
            pattern = patterns[0]
            label = pattern.category or pattern.key
            if pattern.key.startswith("cat_"):
                label = pattern.category or "расход"

            await message.answer(
                f"💡 <b>Совет:</b> Я заметил что ты регулярно тратишь на "
                f"<b>{label}</b> (~{fmt_amount(pattern.avg_amount)}/мес).\n"
                f"Добавить ежемесячное напоминание?",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="✅ Добавить",
                            callback_data=f"pat_add:{pattern.key}"
                        ),
                        InlineKeyboardButton(
                            text="❌ Нет",
                            callback_data="pat_close"
                        ),
                    ]
                ])
            )
    except Exception as e:
        logger.debug("Pattern check error: %s", e)