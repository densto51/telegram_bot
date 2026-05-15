"""
handlers/reminders.py — напоминания о платежах.

Сценарии:
  1. Список → кнопка [🔔 Название] → детали → [🗑 Удалить] / [◀ Назад]
  2. Список → [➕ Добавить] → FSM 4 шага → после создания [🗑 Удалить] / [⏰ Все] / [🏠 Меню]
  3. На каждом шаге FSM → [🏠 Отмена — вернуться в меню]
"""

import re
from datetime import datetime, timedelta
import pytz

from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from config import settings
from database.queries import add_reminder, get_active_reminders, delete_reminder
from keyboards.main_menu import main_menu_kb
from keyboards.reminders import (
    reminders_list_kb,
    reminder_detail_kb,
    repeat_kb,
    after_create_kb,
)
from utils.formatters import fmt_amount, fmt_reminder_dt

router  = Router(name="reminders")
TZ      = pytz.timezone(settings.DEFAULT_TIMEZONE)
DATE_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})\s+(\d{1,2}):(\d{2})$")

REPEAT_LABELS = {
    "none":    "Разово",
    "daily":   "Каждый день",
    "weekly":  "Каждую неделю",
    "monthly": "Каждый месяц",
}
REPEAT_ICONS = {
    "daily": " 🔁 ежедневно",
    "weekly": " 🔁 еженедельно",
    "monthly": " 🔁 ежемесячно",
}


# Кнопки внутри FSM

def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Отмена — вернуться в меню", callback_data="cancel_fsm")]
    ])


def skip_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Пропустить",                callback_data="skip_reminder_amount")],
        [InlineKeyboardButton(text="🏠 Отмена — вернуться в меню", callback_data="cancel_fsm")],
    ])


# FSM состояния

class ReminderStates(StatesGroup):
    waiting_title    = State()
    waiting_amount   = State()
    waiting_datetime = State()
    waiting_repeat   = State()



# СПИСОК НАПОМИНАНИЙ


@router.callback_query(F.data == "reminders")
@router.message(Command("reminders"))
async def show_reminders(event, state=None) -> None:
    msg     = event if isinstance(event, Message) else event.message
    user_id = event.from_user.id
    items   = await get_active_reminders(user_id)

    if not items:
        text = (
            "⏰ <b>Напоминания</b>\n\n"
            "У тебя нет активных напоминаний.\n\n"
            "Нажми <b>➕ Добавить</b> чтобы создать напоминание о платеже."
        )
    else:
        lines = [f"⏰ <b>Напоминания ({len(items)}):</b>\n"]
        for r in items:
            amount_str = f" — {fmt_amount(r['amount'])}" if r["amount"] else ""
            repeat_str = REPEAT_ICONS.get(r["repeat_type"], "")
            lines.append(
                f"🔔 <b>{r['title']}</b>{amount_str}\n"
                f"   📅 {fmt_reminder_dt(r['remind_at'])}{repeat_str}"
            )
        lines.append("\n<i>Нажми на название — чтобы просмотреть\nНажми 🗑 — чтобы удалить</i>")
        text = "\n".join(lines)

    try:
        if isinstance(event, CallbackQuery):
            await event.message.edit_text(text, reply_markup=reminders_list_kb(items))
            await event.answer()
        else:
            await msg.answer(text, reply_markup=reminders_list_kb(items))
    except TelegramBadRequest:
        await msg.answer(text, reply_markup=reminders_list_kb(items))


# ПРОСМОТР ОДНОГО НАПОМИНАНИЯ


@router.callback_query(F.data.startswith("view_reminder:"))
async def cb_view_reminder(callback: CallbackQuery) -> None:
    reminder_id = int(callback.data.split(":")[1])
    user_id     = callback.from_user.id

    items = await get_active_reminders(user_id)
    r     = next((i for i in items if i["id"] == reminder_id), None)

    if not r:
        await callback.answer("❌ Напоминание не найдено", show_alert=True)
        return

    amount_str = f"\n💰 Сумма: <b>{fmt_amount(r['amount'])}</b>" if r["amount"] else ""
    repeat_str = REPEAT_ICONS.get(r["repeat_type"], " разово")
    note_str   = f"\n📝 {r['note']}" if r.get("note") else ""

    text = (
        f"🔔 <b>{r['title']}</b>\n"
        f"📅 {fmt_reminder_dt(r['remind_at'])}"
        f"{amount_str}"
        f"\n🔁{repeat_str}"
        f"{note_str}\n"
        f"\n🆔 #{r['id']}"
    )
    await callback.message.edit_text(text, reply_markup=reminder_detail_kb(reminder_id))
    await callback.answer()



# УДАЛЕНИЕ НАПОМИНАНИЯ


@router.callback_query(F.data.startswith("del_reminder:"))
async def cb_delete_reminder(callback: CallbackQuery) -> None:
    reminder_id = int(callback.data.split(":")[1])
    ok = await delete_reminder(reminder_id, callback.from_user.id)
    if ok:
        await callback.answer("🗑 Напоминание удалено", show_alert=True)
        # Возвращаемся к обновлённому списку
        await show_reminders(callback)
    else:
        await callback.answer("❌ Напоминание не найдено", show_alert=True)



# СОЗДАНИЕ НАПОМИНАНИЯ — FSM


@router.callback_query(F.data == "add_reminder")
async def cb_add_reminder(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_text(
        "⏰ <b>Новое напоминание</b>\n\n"
        "Шаг 1 из 4 — Введи название платежа:\n"
        "<i>Например: Аренда квартиры, Интернет, Кредит</i>",
        reply_markup=cancel_kb(),
    )
    await state.set_state(ReminderStates.waiting_title)
    await callback.answer()


# Шаг 1: название

@router.message(ReminderStates.waiting_title)
async def step_title(message: Message, state: FSMContext) -> None:
    title = message.text.strip()
    if not title:
        await message.answer("❌ Название не может быть пустым:", reply_markup=cancel_kb())
        return
    await state.update_data(title=title)
    await message.answer(
        "Шаг 2 из 4 — Введи сумму платежа (необязательно):",
        reply_markup=skip_cancel_kb(),
    )
    await state.set_state(ReminderStates.waiting_amount)


# Шаг 2: сумма

@router.callback_query(ReminderStates.waiting_amount, F.data == "skip_reminder_amount")
async def cb_skip_amount(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(amount=None)
    await _ask_datetime(callback.message, edit=True)
    await state.set_state(ReminderStates.waiting_datetime)
    await callback.answer()


@router.message(ReminderStates.waiting_amount)
async def step_amount(message: Message, state: FSMContext) -> None:
    try:
        amount = float(message.text.replace(",", ".").replace(" ", ""))
        if amount <= 0:
            raise ValueError
        await state.update_data(amount=amount)
    except ValueError:
        await message.answer(
            "❌ Введи положительное число или нажми «Пропустить»:",
            reply_markup=skip_cancel_kb(),
        )
        return
    await _ask_datetime(message)
    await state.set_state(ReminderStates.waiting_datetime)


async def _ask_datetime(message: Message, edit: bool = False) -> None:
    now     = datetime.now(TZ)
    example = (now + timedelta(days=1)).strftime("%d.%m.%Y %H:%M")
    text = (
        f"Шаг 3 из 4 — Когда напомнить?\n\n"
        f"Формат: <code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n"
        f"Например: <code>{example}</code>"
    )
    if edit:
        await message.edit_text(text, reply_markup=cancel_kb())
    else:
        await message.answer(text, reply_markup=cancel_kb())


# Шаг 3: дата/время

@router.message(ReminderStates.waiting_datetime)
async def step_datetime(message: Message, state: FSMContext) -> None:
    m = DATE_RE.match(message.text.strip())
    if not m:
        await message.answer(
            "❌ Неверный формат.\n"
            "Используй: <code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n"
            "Например: <code>25.12.2026 09:00</code>",
            reply_markup=cancel_kb(),
        )
        return

    day, mon, year, hour, minute = map(int, m.groups())
    try:
        dt = TZ.localize(datetime(year, mon, day, hour, minute))
    except ValueError:
        await message.answer("❌ Некорректная дата. Проверь числа.", reply_markup=cancel_kb())
        return

    if dt <= datetime.now(TZ):
        await message.answer("❌ Дата должна быть в будущем!", reply_markup=cancel_kb())
        return

    await state.update_data(remind_at=dt.isoformat())
    await message.answer(
        "Шаг 4 из 4 — Как часто повторять?",
        reply_markup=repeat_kb(),
    )
    await state.set_state(ReminderStates.waiting_repeat)


# Шаг 4: повтор → сохранение

@router.callback_query(ReminderStates.waiting_repeat, F.data.startswith("repeat:"))
async def step_repeat(callback: CallbackQuery, state: FSMContext) -> None:
    repeat_type = callback.data.split(":")[1]
    data        = await state.get_data()

    repeat_day = None
    if repeat_type == "monthly":
        dt         = datetime.fromisoformat(data["remind_at"])
        repeat_day = dt.day

    reminder_id = await add_reminder(
        user_id=callback.from_user.id,
        title=data["title"],
        remind_at=data["remind_at"],
        amount=data.get("amount"),
        repeat_type=repeat_type,
        repeat_day=repeat_day,
    )

    amount_str = f"\n💰 Сумма: <b>{fmt_amount(data['amount'])}</b>" if data.get("amount") else ""

    await callback.message.edit_text(
        f"✅ <b>Напоминание создано!</b>\n\n"
        f"🔔 <b>{data['title']}</b>"
        f"{amount_str}\n"
        f"📅 {fmt_reminder_dt(data['remind_at'])}\n"
        f"🔁 {REPEAT_LABELS.get(repeat_type, 'Разово')}\n"
        f"🆔 #{reminder_id}\n\n"
        f"<i>Что хочешь сделать дальше?</i>",
        reply_markup=after_create_kb(reminder_id),
    )
    await state.clear()
    await callback.answer("✅ Сохранено!")
