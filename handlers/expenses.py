"""
handlers/expenses.py — запись расходов через FSM.
"""

import re
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from database.queries import add_transaction, get_categories, get_budgets_with_spent
from keyboards.categories import categories_kb
from keyboards.main_menu import main_menu_kb
from utils.formatters import fmt_amount
from utils.parser import parse_expense_text

router = Router(name="expenses")


class ExpenseStates(StatesGroup):
    waiting_amount   = State()
    waiting_category = State()
    waiting_note     = State()


def cancel_kb() -> InlineKeyboardMarkup:
    """Кнопка отмены — возврат в главное меню на любом шаге."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Отмена — вернуться в меню", callback_data="cancel_fsm")]
    ])


def note_kb() -> InlineKeyboardMarkup:
    """Кнопки на шаге заметки."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Пропустить заметку", callback_data="skip_note")],
        [InlineKeyboardButton(text="🏠 Отмена — вернуться в меню", callback_data="cancel_fsm")],
    ])


# ─── Отмена FSM из любого места ──────────────────────────────────────────────

@router.callback_query(F.data == "cancel_fsm")
async def cb_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("🏠 Главное меню:", reply_markup=main_menu_kb())
    await callback.answer()


# ─── Кнопка «Расход» из меню ─────────────────────────────────────────────────

@router.callback_query(F.data == "add_expense")
async def cb_add_expense(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_text(
        "💸 <b>Новый расход</b>\n\n"
        "Введи сумму и описание одним сообщением:\n"
        "<i>Например: «кофе 150» или «150 обед в кафе»</i>",
        reply_markup=cancel_kb(),
    )
    await state.set_state(ExpenseStates.waiting_amount)
    await callback.answer()


@router.message(Command("expense"))
async def cmd_expense(message: Message, state: FSMContext) -> None:
    await message.answer(
        "💸 <b>Новый расход</b>\n\nВведи сумму:",
        reply_markup=cancel_kb(),
    )
    await state.set_state(ExpenseStates.waiting_amount)


# ─── Шаг 1: сумма ────────────────────────────────────────────────────────────

@router.message(ExpenseStates.waiting_amount)
async def step_amount(message: Message, state: FSMContext) -> None:
    parsed = parse_expense_text(message.text or "")
    if not parsed:
        await message.answer(
            "❌ Не могу распознать сумму. Попробуй: <code>кофе 150</code>",
            reply_markup=cancel_kb(),
        )
        return

    await state.update_data(amount=parsed["amount"], note=parsed.get("note"))

    categories = await get_categories(message.from_user.id, is_income=False)
    await message.answer(
        f"💰 Сумма: <b>{fmt_amount(parsed['amount'])}</b>\n"
        + (f"📝 Описание: <i>{parsed['note']}</i>\n\n" if parsed.get("note") else "\n")
        + "Выбери категорию:",
        reply_markup=categories_kb(categories, prefix="exp_cat"),
    )
    await state.set_state(ExpenseStates.waiting_category)


# ─── Шаг 2: категория ────────────────────────────────────────────────────────

@router.callback_query(ExpenseStates.waiting_category, F.data.startswith("exp_cat:"))
async def step_category(callback: CallbackQuery, state: FSMContext) -> None:
    value = callback.data.split(":")[1]
    if value == "skip":
        await _save_expense(callback.message, state, callback.from_user.id)
        await callback.answer()
        return

    await state.update_data(category_id=int(value))
    data = await state.get_data()

    if data.get("note"):
        await _save_expense(callback.message, state, callback.from_user.id)
    else:
        await callback.message.edit_text(
            "📝 Добавить заметку? (необязательно)",
            reply_markup=note_kb(),
        )
        await state.set_state(ExpenseStates.waiting_note)
    await callback.answer()


# ─── Шаг 3: заметка ──────────────────────────────────────────────────────────

@router.callback_query(ExpenseStates.waiting_note, F.data == "skip_note")
async def cb_skip_note(callback: CallbackQuery, state: FSMContext) -> None:
    await _save_expense(callback.message, state, callback.from_user.id)
    await callback.answer()


@router.message(ExpenseStates.waiting_note, Command("skip"))
async def step_note_skip(message: Message, state: FSMContext) -> None:
    await _save_expense(message, state, message.from_user.id)


@router.message(ExpenseStates.waiting_note)
async def step_note(message: Message, state: FSMContext) -> None:
    await state.update_data(note=message.text)
    await _save_expense(message, state, message.from_user.id)


# ─── Сохранение ──────────────────────────────────────────────────────────────

async def _save_expense(message: Message, state: FSMContext, user_id: int) -> None:
    data        = await state.get_data()
    amount      = data["amount"]
    category_id = data.get("category_id")
    note        = data.get("note")
    source      = data.get("source", "text")

    txn_id = await add_transaction(
        user_id=user_id,
        amount=amount,
        category_id=category_id,
        note=note,
        is_income=False,
        source=source,
    )

    budget_warn = ""
    if category_id:
        budgets = await get_budgets_with_spent(user_id)
        for b in budgets:
            if b["spent"] >= b["budget"]:
                pct = b["spent"] / b["budget"] * 100
                budget_warn = (
                    f"\n\n⚠️ <b>Внимание!</b> Бюджет «{b['icon']} {b['name']}» "
                    f"превышен на <b>{pct - 100:.0f}%</b>!"
                )
                break
            elif b["spent"] / b["budget"] >= 0.85:
                budget_warn = (
                    f"\n\n⚠️ Бюджет «{b['icon']} {b['name']}» использован "
                    f"на <b>{b['spent'] / b['budget'] * 100:.0f}%</b>"
                )
                break

    await message.answer(
        f"✅ <b>Расход записан!</b>\n\n"
        f"💸 Сумма: <b>{fmt_amount(amount)}</b>\n"
        + (f"📝 {note}\n" if note else "")
        + f"🆔 #{txn_id}"
        + budget_warn,
        reply_markup=main_menu_kb(),
    )
    await state.clear()


# ─── Удаление транзакции ─────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("del_txn:"))
async def cb_delete_txn(callback: CallbackQuery) -> None:
    from database.queries import delete_transaction
    txn_id = int(callback.data.split(":")[1])
    ok = await delete_transaction(txn_id, callback.from_user.id)
    if ok:
        await callback.answer("🗑 Транзакция удалена", show_alert=True)
        await callback.message.edit_text("🗑 Транзакция удалена.", reply_markup=main_menu_kb())
    else:
        await callback.answer("❌ Не найдено", show_alert=True)