"""
handlers/income.py — запись доходов через FSM.
"""

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from database.queries import add_transaction, get_categories
from keyboards.categories import categories_kb
from keyboards.main_menu import main_menu_kb
from utils.formatters import fmt_amount
from utils.parser import parse_expense_text

router = Router(name="income")


class IncomeStates(StatesGroup):
    waiting_amount   = State()
    waiting_category = State()
    waiting_note     = State()


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Отмена — вернуться в меню", callback_data="cancel_fsm")]
    ])


def note_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Пропустить заметку", callback_data="skip_income_note")],
        [InlineKeyboardButton(text="🏠 Отмена — вернуться в меню", callback_data="cancel_fsm")],
    ])


# ─── Кнопка «Доход» из меню ──────────────────────────────────────────────────

@router.callback_query(F.data == "add_income")
async def cb_add_income(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_text(
        "💚 <b>Новый доход</b>\n\n"
        "Введи сумму и источник:\n"
        "<i>Например: «зарплата 50000» или «30000 фриланс»</i>",
        reply_markup=cancel_kb(),
    )
    await state.set_state(IncomeStates.waiting_amount)
    await callback.answer()


@router.message(Command("income"))
async def cmd_income(message: Message, state: FSMContext) -> None:
    await message.answer(
        "💚 <b>Новый доход</b>\n\nВведи сумму:",
        reply_markup=cancel_kb(),
    )
    await state.set_state(IncomeStates.waiting_amount)


# ─── Шаг 1: сумма ────────────────────────────────────────────────────────────

@router.message(IncomeStates.waiting_amount)
async def step_amount(message: Message, state: FSMContext) -> None:
    parsed = parse_expense_text(message.text or "")
    if not parsed:
        await message.answer(
            "❌ Не могу распознать сумму. Пример: <code>зарплата 50000</code>",
            reply_markup=cancel_kb(),
        )
        return
    await state.update_data(amount=parsed["amount"], note=parsed.get("note"))
    categories = await get_categories(message.from_user.id, is_income=True)
    await message.answer(
        f"💰 Сумма: <b>{fmt_amount(parsed['amount'])}</b>\n\nВыбери источник дохода:",
        reply_markup=categories_kb(categories, prefix="inc_cat"),
    )
    await state.set_state(IncomeStates.waiting_category)


# ─── Шаг 2: категория ────────────────────────────────────────────────────────

@router.callback_query(IncomeStates.waiting_category, F.data.startswith("inc_cat:"))
async def step_category(callback: CallbackQuery, state: FSMContext) -> None:
    value = callback.data.split(":")[1]
    if value == "skip":
        await _save_income(callback.message, state, callback.from_user.id)
        await callback.answer()
        return

    await state.update_data(category_id=int(value))
    data = await state.get_data()

    if data.get("note"):
        await _save_income(callback.message, state, callback.from_user.id)
    else:
        await callback.message.edit_text(
            "📝 Добавить заметку? (необязательно)",
            reply_markup=note_kb(),
        )
        await state.set_state(IncomeStates.waiting_note)
    await callback.answer()


# ─── Шаг 3: заметка ──────────────────────────────────────────────────────────

@router.callback_query(IncomeStates.waiting_note, F.data == "skip_income_note")
async def cb_skip_note(callback: CallbackQuery, state: FSMContext) -> None:
    await _save_income(callback.message, state, callback.from_user.id)
    await callback.answer()


@router.message(IncomeStates.waiting_note, Command("skip"))
async def step_note_skip(message: Message, state: FSMContext) -> None:
    await _save_income(message, state, message.from_user.id)


@router.message(IncomeStates.waiting_note)
async def step_note(message: Message, state: FSMContext) -> None:
    await state.update_data(note=message.text)
    await _save_income(message, state, message.from_user.id)


# ─── Сохранение ──────────────────────────────────────────────────────────────

async def _save_income(message: Message, state: FSMContext, user_id: int) -> None:
    data = await state.get_data()
    txn_id = await add_transaction(
        user_id=user_id,
        amount=data["amount"],
        category_id=data.get("category_id"),
        note=data.get("note"),
        is_income=True,
        source=data.get("source", "text"),
    )
    await message.answer(
        f"✅ <b>Доход записан!</b>\n\n"
        f"💚 Сумма: <b>{fmt_amount(data['amount'])}</b>\n"
        + (f"📝 {data['note']}\n" if data.get("note") else "")
        + f"🆔 #{txn_id}",
        reply_markup=main_menu_kb(),
    )
    await state.clear()