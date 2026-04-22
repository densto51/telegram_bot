"""
handlers/expenses.py — запись расходов через FSM.

Сценарий:
  1. Пользователь нажимает «➖ Расход» ИЛИ пишет «кофе 150»
  2. Если сумма не распознана — бот просит ввести
  3. Выбор категории (inline-клавиатура)
  4. Опциональная заметка
  5. Сохранение в БД + проверка бюджета
"""

import re
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from database.queries import add_transaction, get_categories, get_budgets_with_spent
from keyboards.categories import categories_kb
from keyboards.main_menu import main_menu_kb
from utils.formatters import fmt_amount
from utils.parser import parse_expense_text

router = Router(name="expenses")

# ─── Паттерн для быстрого ввода: «кофе 150» или «150 кофе» ─────────────────
QUICK_PATTERN = re.compile(
    r"^(?P<note>.+?)\s+(?P<amount>\d+[\.,]?\d*)\s*$"
    r"|^(?P<amount2>\d+[\.,]?\d*)\s+(?P<note2>.+)$"
)


class ExpenseStates(StatesGroup):
    waiting_amount = State()
    waiting_category = State()
    waiting_note = State()


# ─── Кнопка «Расход» из меню ─────────────────────────────────────────────────

@router.callback_query(F.data == "add_expense")
async def cb_add_expense(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_text(
        "💸 <b>Новый расход</b>\n\n"
        "Введи сумму и описание одним сообщением:\n"
        "<i>Например: «кофе 150» или «150 обед в кафе»</i>\n\n"
        "Или просто введи сумму цифрами:",
    )
    await state.set_state(ExpenseStates.waiting_amount)
    await callback.answer()


# ─── Быстрый ввод из любого контекста ────────────────────────────────────────

@router.message(Command("expense"))
async def cmd_expense(message: Message, state: FSMContext) -> None:
    await message.answer(
        "💸 <b>Новый расход</b>\n\nВведи сумму:"
    )
    await state.set_state(ExpenseStates.waiting_amount)


# ─── Шаг 1: получение суммы/текста ───────────────────────────────────────────

@router.message(ExpenseStates.waiting_amount)
async def step_amount(message: Message, state: FSMContext) -> None:
    parsed = parse_expense_text(message.text or "")
    if not parsed:
        await message.answer("❌ Не могу распознать сумму. Попробуй: <code>кофе 150</code>")
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


# ─── Шаг 2: выбор категории ───────────────────────────────────────────────────

@router.callback_query(ExpenseStates.waiting_category, F.data.startswith("exp_cat:"))
async def step_category(callback: CallbackQuery, state: FSMContext) -> None:
    cat_id = int(callback.data.split(":")[1])
    await state.update_data(category_id=cat_id)

    data = await state.get_data()
    note = data.get("note")

    if note:
        # Заметка уже есть — сохраняем
        await _save_expense(callback.message, state, callback.from_user.id)
    else:
        await callback.message.edit_text(
            "📝 Добавить заметку? (необязательно)\n"
            "Напиши что-нибудь или нажми /skip"
        )
        await state.set_state(ExpenseStates.waiting_note)
    await callback.answer()


@router.callback_query(ExpenseStates.waiting_category, F.data == "exp_cat:skip")
async def step_category_skip(callback: CallbackQuery, state: FSMContext) -> None:
    await _save_expense(callback.message, state, callback.from_user.id)
    await callback.answer()


# ─── Шаг 3: заметка ──────────────────────────────────────────────────────────

@router.message(ExpenseStates.waiting_note, Command("skip"))
async def step_note_skip(message: Message, state: FSMContext) -> None:
    await _save_expense(message, state, message.from_user.id)


@router.message(ExpenseStates.waiting_note)
async def step_note(message: Message, state: FSMContext) -> None:
    await state.update_data(note=message.text)
    await _save_expense(message, state, message.from_user.id)


# ─── Сохранение ───────────────────────────────────────────────────────────────

async def _save_expense(
    message: Message, state: FSMContext, user_id: int
) -> None:
    data = await state.get_data()
    amount: float = data["amount"]
    category_id: int | None = data.get("category_id")
    note: str | None = data.get("note")
    source: str = data.get("source", "text")

    txn_id = await add_transaction(
        user_id=user_id,
        amount=amount,
        category_id=category_id,
        note=note,
        is_income=False,
        source=source,
    )

    # ── Проверка бюджета ─────────────────────────────────────────────
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


# ─── Удаление последней транзакции ───────────────────────────────────────────

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
