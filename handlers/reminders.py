"""
handlers/reminders.py — создание и управление напоминаниями о платежах.

FSM:
  1. Название платежа
  2. Сумма (опционально)
  3. Дата и время (DD.MM.YYYY HH:MM)
  4. Повторение (none / daily / weekly / monthly)
  5. Сохранение → APScheduler подхватывает
"""

import re
from datetime import datetime, timedelta
import pytz

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from config import settings
from database.queries import (
    add_reminder,
    get_active_reminders,
    delete_reminder,
)
from keyboards.main_menu import main_menu_kb
from keyboards.reminders import reminders_list_kb, repeat_kb
from utils.formatters import fmt_amount, fmt_reminder_dt

router = Router(name="reminders")

TZ = pytz.timezone(settings.DEFAULT_TIMEZONE)
DATE_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})\s+(\d{1,2}):(\d{2})$")


class ReminderStates(StatesGroup):
    waiting_title = State()
    waiting_amount = State()
    waiting_datetime = State()
    waiting_repeat = State()


# ─── Список напоминаний ──────────────────────────────────────────────────────

@router.callback_query(F.data == "reminders")
@router.message(Command("reminders"))
async def show_reminders(event, state=None) -> None:
    msg = event if isinstance(event, Message) else event.message
    user_id = event.from_user.id

    reminders = await get_active_reminders(user_id)
    if not reminders:
        text = (
            "⏰ <b>Напоминания</b>\n\n"
            "У тебя нет активных напоминаний.\n\n"
            "Добавь напоминание о предстоящем платеже!"
        )
    else:
        lines = [f"⏰ <b>Активные напоминания ({len(reminders)}):</b>\n"]
        for r in reminders:
            amount_str = f" — {fmt_amount(r['amount'])}" if r["amount"] else ""
            repeat_str = {
                "daily": " 🔁 ежедневно",
                "weekly": " 🔁 еженедельно",
                "monthly": " 🔁 ежемесячно",
            }.get(r["repeat_type"], "")
            lines.append(
                f"🔔 <b>{r['title']}</b>{amount_str}\n"
                f"   📅 {fmt_reminder_dt(r['remind_at'])}{repeat_str}\n"
                + (f"   📝 {r['note']}\n" if r.get("note") else "")
            )
        text = "\n".join(lines)

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=reminders_list_kb(reminders))
        await event.answer()
    else:
        await msg.answer(text, reply_markup=reminders_list_kb(reminders))


# ─── Создание напоминания: шаг 1 — название ──────────────────────────────────

@router.callback_query(F.data == "add_reminder")
async def cb_add_reminder(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_text(
        "⏰ <b>Новое напоминание</b>\n\n"
        "Шаг 1/4 — Введи название платежа:\n"
        "<i>Например: Аренда квартиры, Интернет, Кредит</i>"
    )
    await state.set_state(ReminderStates.waiting_title)
    await callback.answer()


@router.message(ReminderStates.waiting_title)
async def step_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=message.text.strip())
    await message.answer(
        "Шаг 2/4 — Введи сумму платежа (или /skip если не нужно):"
    )
    await state.set_state(ReminderStates.waiting_amount)


# ─── Шаг 2 — сумма ───────────────────────────────────────────────────────────

@router.message(ReminderStates.waiting_amount, Command("skip"))
async def step_amount_skip(message: Message, state: FSMContext) -> None:
    await state.update_data(amount=None)
    await _ask_datetime(message)
    await state.set_state(ReminderStates.waiting_datetime)


@router.message(ReminderStates.waiting_amount)
async def step_amount(message: Message, state: FSMContext) -> None:
    try:
        amount = float(message.text.replace(",", ".").replace(" ", ""))
        if amount <= 0:
            raise ValueError
        await state.update_data(amount=amount)
    except ValueError:
        await message.answer("❌ Введи число или /skip:")
        return
    await _ask_datetime(message)
    await state.set_state(ReminderStates.waiting_datetime)


async def _ask_datetime(message: Message) -> None:
    now = datetime.now(TZ)
    example = (now + timedelta(days=1)).strftime("%d.%m.%Y %H:%M")
    await message.answer(
        f"Шаг 3/4 — Когда напомнить?\n\n"
        f"Формат: <code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n"
        f"Например: <code>{example}</code>"
    )


# ─── Шаг 3 — дата/время ──────────────────────────────────────────────────────

@router.message(ReminderStates.waiting_datetime)
async def step_datetime(message: Message, state: FSMContext) -> None:
    m = DATE_RE.match(message.text.strip())
    if not m:
        await message.answer(
            "❌ Неверный формат. Используй: <code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n"
            "Например: <code>25.12.2025 09:00</code>"
        )
        return

    day, month, year, hour, minute = map(int, m.groups())
    try:
        dt = TZ.localize(datetime(year, month, day, hour, minute))
    except ValueError:
        await message.answer("❌ Некорректная дата. Проверь числа.")
        return

    if dt <= datetime.now(TZ):
        await message.answer("❌ Дата должна быть в будущем!")
        return

    await state.update_data(remind_at=dt.isoformat())
    await message.answer(
        f"Шаг 4/4 — Повторять напоминание?",
        reply_markup=repeat_kb(),
    )
    await state.set_state(ReminderStates.waiting_repeat)


# ─── Шаг 4 — повтор ──────────────────────────────────────────────────────────

@router.callback_query(ReminderStates.waiting_repeat, F.data.startswith("repeat:"))
async def step_repeat(callback: CallbackQuery, state: FSMContext) -> None:
    repeat_type = callback.data.split(":")[1]
    await state.update_data(repeat_type=repeat_type)
    data = await state.get_data()

    repeat_day = None
    if repeat_type == "monthly":
        dt = datetime.fromisoformat(data["remind_at"])
        repeat_day = dt.day

    reminder_id = await add_reminder(
        user_id=callback.from_user.id,
        title=data["title"],
        remind_at=data["remind_at"],
        amount=data.get("amount"),
        repeat_type=repeat_type,
        repeat_day=repeat_day,
        note=data.get("note"),
    )

    repeat_labels = {
        "none": "Разово",
        "daily": "Каждый день",
        "weekly": "Каждую неделю",
        "monthly": "Каждый месяц",
    }
    amount_str = f" — {fmt_amount(data['amount'])}" if data.get("amount") else ""

    await callback.message.edit_text(
        f"✅ <b>Напоминание создано!</b>\n\n"
        f"🔔 {data['title']}{amount_str}\n"
        f"📅 {fmt_reminder_dt(data['remind_at'])}\n"
        f"🔁 {repeat_labels.get(repeat_type, 'Разово')}\n"
        f"🆔 #{reminder_id}",
        reply_markup=main_menu_kb(),
    )
    await state.clear()
    await callback.answer()


# ─── Удаление напоминания ─────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("del_reminder:"))
async def cb_delete_reminder(callback: CallbackQuery) -> None:
    reminder_id = int(callback.data.split(":")[1])
    ok = await delete_reminder(reminder_id, callback.from_user.id)
    if ok:
        await callback.answer("🗑 Напоминание удалено", show_alert=True)
        await show_reminders(callback)
    else:
        await callback.answer("❌ Не найдено", show_alert=True)
