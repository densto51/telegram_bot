"""
handlers/goals.py - Финансовые цели (накопления).

Сценарий:
  1. Создать цель: название → сумма → иконка
  2. Пополнить цель вручную
  3. Просмотреть прогресс с визуальным баром
  4. Удалить цель

Хранение: таблица goals в SQLite3
"""

import logging
from datetime import datetime

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.exceptions import TelegramBadRequest

from database.db import get_db
from keyboards.main_menu import main_menu_kb
from utils.formatters import fmt_amount, fmt_progress_bar

logger = logging.getLogger(__name__)
router = Router(name="goals")

GOAL_ICONS = ["🎯","✈️","🏠","🚗","💻","📱","👗","🎓","💍","🏖️",
              "🏋️","🎸","📷","🐶","💰","🛒","🎮","🌍","⚽","🎁"]


# SQL HELPERS
async def _init_goals_table() -> None:
    async with get_db() as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS goals (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                title       TEXT    NOT NULL,
                icon        TEXT    NOT NULL DEFAULT '🎯',
                target      REAL    NOT NULL CHECK(target > 0),
                saved       REAL    NOT NULL DEFAULT 0,
                deadline    TEXT,
                is_done     INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_goals_user ON goals(user_id, is_done);
        """)
        await db.commit()


async def _get_goals(user_id: int) -> list[dict]:
    async with get_db() as db:
        rows = await (await db.execute(
            "SELECT * FROM goals WHERE user_id=? AND is_done=0 ORDER BY created_at DESC",
            (user_id,)
        )).fetchall()
    return [dict(r) for r in rows]


async def _get_goal(goal_id: int, user_id: int) -> dict | None:
    async with get_db() as db:
        row = await (await db.execute(
            "SELECT * FROM goals WHERE id=? AND user_id=?",
            (goal_id, user_id)
        )).fetchone()
    return dict(row) if row else None


async def _create_goal(user_id: int, title: str, icon: str,
                       target: float, deadline: str | None) -> int:
    async with get_db() as db:
        cur = await db.execute(
            "INSERT INTO goals(user_id,title,icon,target,deadline) VALUES(?,?,?,?,?)",
            (user_id, title, icon, target, deadline)
        )
        await db.commit()
        return cur.lastrowid


async def _add_savings(goal_id: int, user_id: int, amount: float) -> dict | None:
    async with get_db() as db:
        await db.execute(
            "UPDATE goals SET saved = saved + ? WHERE id=? AND user_id=?",
            (amount, goal_id, user_id)
        )
        # Проверяем достижение цели
        await db.execute(
            "UPDATE goals SET is_done=1 WHERE id=? AND user_id=? AND saved >= target",
            (goal_id, user_id)
        )
        await db.commit()
    return await _get_goal(goal_id, user_id)


async def _delete_goal(goal_id: int, user_id: int) -> bool:
    async with get_db() as db:
        cur = await db.execute(
            "DELETE FROM goals WHERE id=? AND user_id=?",
            (goal_id, user_id)
        )
        await db.commit()
    return cur.rowcount > 0


async def _get_completed_goals(user_id: int) -> list[dict]:
    async with get_db() as db:
        rows = await (await db.execute(
            "SELECT * FROM goals WHERE user_id=? AND is_done=1 ORDER BY created_at DESC LIMIT 5",
            (user_id,)
        )).fetchall()
    return [dict(r) for r in rows]


# FSM STATES
class GoalStates(StatesGroup):
    waiting_title    = State()
    waiting_target   = State()
    waiting_icon     = State()
    waiting_deadline = State()
    waiting_deposit  = State()


# KEYBOARDS
def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Отмена", callback_data="cancel_fsm")]
    ])


def skip_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Пропустить", callback_data="skip_goal_deadline")],
        [InlineKeyboardButton(text="🏠 Отмена",     callback_data="cancel_fsm")],
    ])


def goals_list_kb(goals: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for g in goals:
        pct = min(g["saved"] / g["target"] * 100, 100) if g["target"] else 0
        rows.append([
            InlineKeyboardButton(
                text=f"{g['icon']} {g['title']} ({pct:.0f}%)",
                callback_data=f"goal_view:{g['id']}"
            )
        ])
    rows += [
        [InlineKeyboardButton(text="➕ Новая цель",   callback_data="goal_add")],
        [InlineKeyboardButton(text="🏆 Достигнутые", callback_data="goals_done")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def goal_detail_kb(goal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Пополнить",      callback_data=f"goal_deposit:{goal_id}")],
        [InlineKeyboardButton(text="🗑 Удалить цель",   callback_data=f"goal_delete:{goal_id}")],
        [InlineKeyboardButton(text="◀ К списку целей", callback_data="goals")],
        [InlineKeyboardButton(text="🏠 Меню",           callback_data="main_menu")],
    ])


def icons_kb() -> InlineKeyboardMarkup:
    rows = []
    row = []
    for i, icon in enumerate(GOAL_ICONS):
        row.append(InlineKeyboardButton(text=icon, callback_data=f"goal_icon:{icon}"))
        if len(row) == 5:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="🏠 Отмена", callback_data="cancel_fsm")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# HELPERS
def _goal_card(g: dict) -> str:
    saved  = g["saved"]
    target = g["target"]
    pct    = min(saved / target * 100, 100) if target else 0
    bar    = fmt_progress_bar(saved, target, width=12)
    remain = max(target - saved, 0)

    # Прогноз (если есть дедлайн)
    deadline_str = ""
    if g.get("deadline"):
        deadline_str = f"\n📅 Дедлайн: <b>{g['deadline']}</b>"

    done_str = "\n\n🎉 <b>ЦЕЛЬ ДОСТИГНУТА!</b>" if g["is_done"] else ""

    return (
        f"{g['icon']} <b>{g['title']}</b>\n\n"
        f"{bar} <b>{pct:.1f}%</b>\n\n"
        f"💰 Накоплено: <b>{fmt_amount(saved)}</b>\n"
        f"🎯 Цель:      <b>{fmt_amount(target)}</b>\n"
        f"📉 Осталось:  <b>{fmt_amount(remain)}</b>"
        f"{deadline_str}"
        f"{done_str}"
    )

# HANDLERS
@router.message(Command("goals"))
@router.callback_query(F.data == "goals")
async def show_goals(event, state=None) -> None:
    await _init_goals_table()
    msg     = event if isinstance(event, Message) else event.message
    user_id = event.from_user.id
    goals   = await _get_goals(user_id)

    if not goals:
        text = (
            "🎯 <b>Финансовые цели</b>\n\n"
            "У тебя пока нет активных целей.\n\n"
            "Создай первую цель — например:\n"
            "  ✈️ Отпуск в Турции — 150 000 с\n"
            "  💻 Новый ноутбук — 80 000 с\n"
            "  🚗 Автомобиль — 500 000 с"
        )
    else:
        lines = [f"🎯 <b>Финансовые цели ({len(goals)}):</b>\n"]
        for g in goals:
            saved  = g["saved"]
            target = g["target"]
            pct    = min(saved / target * 100, 100) if target else 0
            bar    = fmt_progress_bar(saved, target, width=10)
            lines.append(
                f"{g['icon']} <b>{g['title']}</b>\n"
                f"  {bar} {pct:.0f}%\n"
                f"  {fmt_amount(saved)} из {fmt_amount(target)}\n"
            )
        text = "\n".join(lines)

    try:
        if isinstance(event, CallbackQuery):
            await event.message.edit_text(text, reply_markup=goals_list_kb(goals))
            await event.answer()
        else:
            await msg.answer(text, reply_markup=goals_list_kb(goals))
    except TelegramBadRequest:
        await msg.answer(text, reply_markup=goals_list_kb(goals))


# Просмотр цели
@router.callback_query(F.data.startswith("goal_view:"))
async def cb_goal_view(callback: CallbackQuery) -> None:
    goal_id = int(callback.data.split(":")[1])
    g = await _get_goal(goal_id, callback.from_user.id)
    if not g:
        await callback.answer("❌ Цель не найдена", show_alert=True)
        return
    await callback.message.edit_text(_goal_card(g), reply_markup=goal_detail_kb(goal_id))
    await callback.answer()


# Создание цели: шаг 1 — название
@router.callback_query(F.data == "goal_add")
async def cb_goal_add(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_text(
        "🎯 <b>Новая цель</b>\n\n"
        "Шаг 1 из 4 — Введи название:\n"
        "<i>Например: Отпуск в Турции, Новый Samsung, Ноутбук</i>",
        reply_markup=cancel_kb(),
    )
    await state.set_state(GoalStates.waiting_title)
    await callback.answer()


@router.message(GoalStates.waiting_title)
async def step_title(message: Message, state: FSMContext) -> None:
    title = message.text.strip()
    if not title or len(title) > 50:
        await message.answer("❌ Название должно быть от 1 до 50 символов:", reply_markup=cancel_kb())
        return
    await state.update_data(title=title)
    await message.answer(
        "Шаг 2 из 4 — Введи сумму цели:\n"
        "<i>Например: 150000 или 80000</i>",
        reply_markup=cancel_kb(),
    )
    await state.set_state(GoalStates.waiting_target)


#Шаг 2 — целевая сумма
@router.message(GoalStates.waiting_target)
async def step_target(message: Message, state: FSMContext) -> None:
    try:
        amount = float(message.text.replace(",", ".").replace(" ", ""))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи положительное число:", reply_markup=cancel_kb())
        return
    await state.update_data(target=amount)
    await message.answer(
        "Шаг 3 из 4 — Выбери иконку для цели:",
        reply_markup=icons_kb(),
    )
    await state.set_state(GoalStates.waiting_icon)


#Шаг 3 — иконка
@router.callback_query(GoalStates.waiting_icon, F.data.startswith("goal_icon:"))
async def step_icon(callback: CallbackQuery, state: FSMContext) -> None:
    icon = callback.data.split(":")[1]
    await state.update_data(icon=icon)
    await callback.message.edit_text(
        "Шаг 4 из 4 — Укажи дедлайн (необязательно):\n\n"
        "Формат: <code>ДД.ММ.ГГГГ</code>\n"
        "Например: <code>31.12.2025</code>",
        reply_markup=skip_cancel_kb(),
    )
    await state.set_state(GoalStates.waiting_deadline)
    await callback.answer()


# Шаг 4 - дедлайн
@router.callback_query(GoalStates.waiting_deadline, F.data == "skip_goal_deadline")
async def step_deadline_skip(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(deadline=None)
    await _save_goal(callback.message, state, callback.from_user.id)
    await callback.answer()

@router.message(GoalStates.waiting_deadline)
async def step_deadline(message: Message, state: FSMContext) -> None:
    import re
    m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", message.text.strip())
    if not m:
        await message.answer(
            "❌ Неверный формат. Используй: <code>ДД.ММ.ГГГГ</code>",
            reply_markup=skip_cancel_kb()
        )
        return
    day, mon, year = map(int, m.groups())
    try:
        deadline_dt = datetime(year, mon, day)
        if deadline_dt.date() <= datetime.now().date():
            await message.answer("❌ Дедлайн должен быть в будущем!", reply_markup=skip_cancel_kb())
            return
        await state.update_data(deadline=message.text.strip())
    except ValueError:
        await message.answer("❌ Некорректная дата.", reply_markup=skip_cancel_kb())
        return
    await _save_goal(message, state, message.from_user.id)


async def _save_goal(message: Message, state: FSMContext, user_id: int) -> None:
    data     = await state.get_data()
    goal_id  = await _create_goal(
        user_id=user_id,
        title=data["title"],
        icon=data["icon"],
        target=data["target"],
        deadline=data.get("deadline"),
    )
    deadline_str = f"\n📅 Дедлайн: {data['deadline']}" if data.get("deadline") else ""
    await message.answer(
        f"✅ <b>Цель создана!</b>\n\n"
        f"{data['icon']} <b>{data['title']}</b>\n"
        f"🎯 Цель: <b>{fmt_amount(data['target'])}</b>"
        f"{deadline_str}\n\n"
        f"Теперь пополняй цель кнопкой 💰 Пополнить!\n"
        f"🆔 #{goal_id}",
        reply_markup=goal_detail_kb(goal_id),
    )
    await state.clear()


# Пополнение цели
@router.callback_query(F.data.startswith("goal_deposit:"))
async def cb_goal_deposit(callback: CallbackQuery, state: FSMContext) -> None:
    goal_id = int(callback.data.split(":")[1])
    g = await _get_goal(goal_id, callback.from_user.id)
    if not g:
        await callback.answer("❌ Цель не найдена", show_alert=True)
        return
    remain = max(g["target"] - g["saved"], 0)
    await state.update_data(goal_id=goal_id)
    await callback.message.edit_text(
        f"💰 <b>Пополнение цели</b>\n\n"
        f"{g['icon']} {g['title']}\n"
        f"Осталось накопить: <b>{fmt_amount(remain)}</b>\n\n"
        f"Введи сумму пополнения:",
        reply_markup=cancel_kb(),
    )
    await state.set_state(GoalStates.waiting_deposit)
    await callback.answer()


@router.message(GoalStates.waiting_deposit)
async def step_deposit(message: Message, state: FSMContext) -> None:
    try:
        amount = float(message.text.replace(",", ".").replace(" ", ""))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи положительное число:", reply_markup=cancel_kb())
        return

    data    = await state.get_data()
    goal_id = data["goal_id"]
    g       = await _add_savings(goal_id, message.from_user.id, amount)

    if not g:
        await message.answer("❌ Цель не найдена.", reply_markup=main_menu_kb())
        await state.clear()
        return

    await state.clear()

    # Цель достигнута?
    if g["is_done"]:
        await message.answer(
            f"🎉 <b>ПОЗДРАВЛЯЕМ! Цель достигнута! юхууу</b>\n\n"
            f"{_goal_card(g)}\n\n"
            f"Ты накопил(а) <b>{fmt_amount(g['target'])}</b>! 🥳",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎯 К целям", callback_data="goals")],
                [InlineKeyboardButton(text="🏠 Меню",    callback_data="main_menu")],
            ])
        )
    else:
        await message.answer(
            f"✅ Пополнено на <b>{fmt_amount(amount)}</b>!\n\n"
            f"{_goal_card(g)}",
            reply_markup=goal_detail_kb(goal_id),
        )


# Удаление цели
@router.callback_query(F.data.startswith("goal_delete:"))
async def cb_goal_delete(callback: CallbackQuery) -> None:
    goal_id = int(callback.data.split(":")[1])
    ok = await _delete_goal(goal_id, callback.from_user.id)
    if ok:
        await callback.answer("🗑 Цель удалена", show_alert=True)
        await show_goals(callback)
    else:
        await callback.answer("❌ Не найдено", show_alert=True)


# Достигнутые цели
@router.callback_query(F.data == "goals_done")
async def cb_goals_done(callback: CallbackQuery) -> None:
    goals = await _get_completed_goals(callback.from_user.id)
    if not goals:
        await callback.answer("Пока нет достигнутых целей 💪", show_alert=True)
        return
    lines = ["🏆 <b>Достигнутые цели:</b>\n"]
    for g in goals:
        lines.append(f"✅ {g['icon']} {g['title']} — {fmt_amount(g['target'])}")
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀ К активным целям", callback_data="goals")],
            [InlineKeyboardButton(text="🏠 Меню",             callback_data="main_menu")],
        ])
    )
    await callback.answer()