"""
handlers/budget.py — управление бюджетами по категориям.
"""

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from database.queries import (
    get_budgets_with_spent,
    set_budget,
    delete_budget,
    get_categories,
    set_monthly_limit,
    get_user_settings,
)
from keyboards.categories import categories_kb
from keyboards.main_menu import main_menu_kb
from keyboards.budget import budget_list_kb
from utils.formatters import fmt_amount, fmt_progress_bar

router = Router(name="budget")


class BudgetStates(StatesGroup):
    waiting_category = State()
    waiting_amount = State()
    waiting_global_limit = State()


#Просмотр бюджетов

@router.callback_query(F.data == "budget")
@router.message(Command("budget"))
async def show_budget(event, state: FSMContext = None) -> None:
    msg = event if isinstance(event, Message) else event.message
    user_id = event.from_user.id

    budgets = await get_budgets_with_spent(user_id)
    settings_row = await get_user_settings(user_id)
    global_limit = settings_row["monthly_limit"] if settings_row else None

    if not budgets and not global_limit:
        text = (
            "🎯 <b>Бюджеты</b>\n\n"
            "У тебя пока нет настроенных бюджетов.\n\n"
            "Нажми <b>➕ Добавить</b> чтобы задать лимит расходов по категории."
        )
    else:
        lines = ["🎯 <b>Бюджеты на текущий месяц:</b>\n"]

        if global_limit:
            from database.queries import get_monthly_summary
            from datetime import datetime
            now = datetime.now()
            summary = await get_monthly_summary(user_id, now.year, now.month)
            spent = summary["total_expenses"]
            pct = spent / global_limit * 100
            bar = fmt_progress_bar(spent, global_limit)
            lines.append(
                f"🌍 <b>Общий лимит:</b> {fmt_amount(global_limit)}\n"
                f"{bar} {pct:.0f}%\n"
                f"  Потрачено: {fmt_amount(spent)}\n"
                f"  Остаток: {fmt_amount(max(0, global_limit - spent))}\n"
            )

        for b in budgets:
            pct = b["spent"] / b["budget"] * 100 if b["budget"] else 0
            bar = fmt_progress_bar(b["spent"], b["budget"])
            status = "🔴" if pct >= 100 else ("🟡" if pct >= 80 else "🟢")
            lines.append(
                f"{status} {b['icon']} <b>{b['name']}</b>\n"
                f"  {bar} {pct:.0f}%\n"
                f"  {fmt_amount(b['spent'])} / {fmt_amount(b['budget'])}\n"
            )
        text = "\n".join(lines)

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=budget_list_kb(budgets))
        await event.answer()
    else:
        await msg.answer(text, reply_markup=budget_list_kb(budgets))


#  Добавление бюджета

@router.callback_query(F.data == "budget_add")
async def cb_budget_add(callback: CallbackQuery, state: FSMContext) -> None:
    categories = await get_categories(callback.from_user.id, is_income=False)
    await callback.message.edit_text(
        "🎯 <b>Новый бюджет</b>\n\nВыбери категорию:",
        reply_markup=categories_kb(categories, prefix="bcat"),
    )
    await state.set_state(BudgetStates.waiting_category)
    await callback.answer()


@router.callback_query(BudgetStates.waiting_category, F.data.startswith("bcat:"))
async def cb_budget_category(callback: CallbackQuery, state: FSMContext) -> None:
    cat_id = int(callback.data.split(":")[1])
    await state.update_data(category_id=cat_id)
    await callback.message.edit_text(
        "💰 Введи лимит на месяц (сумму цифрами):"
    )
    await state.set_state(BudgetStates.waiting_amount)
    await callback.answer()


@router.message(BudgetStates.waiting_amount)
async def step_budget_amount(message: Message, state: FSMContext) -> None:
    try:
        amount = float(message.text.replace(",", ".").replace(" ", ""))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи положительное число:")
        return

    data = await state.get_data()
    await set_budget(message.from_user.id, data["category_id"], amount)
    await message.answer(
        f"✅ Бюджет <b>{fmt_amount(amount)}/мес</b> установлен!",
        reply_markup=main_menu_kb(),
    )
    await state.clear()


# Удаление бюджета

@router.callback_query(F.data.startswith("budget_delete:"))
async def cb_budget_delete(callback: CallbackQuery) -> None:
    budget_id = int(callback.data.split(":")[1])
    ok = await delete_budget(budget_id, callback.from_user.id)
    if ok:
        await callback.answer("🗑 Бюджет удалён", show_alert=True)
    else:
        await callback.answer("❌ Не найдено", show_alert=True)
    await show_budget(callback)


# Глобальный лимит расходов

@router.callback_query(F.data == "set_global_limit")
async def cb_set_global_limit(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_text(
        "🌍 <b>Общий лимит расходов в месяц</b>\n\n"
        "Введи сумму или /remove чтобы убрать лимит:"
    )
    await state.set_state(BudgetStates.waiting_global_limit)
    await callback.answer()


@router.message(BudgetStates.waiting_global_limit, F.text == "/remove")
async def step_remove_limit(message: Message, state: FSMContext) -> None:
    await set_monthly_limit(message.from_user.id, None)
    await message.answer("✅ Общий лимит убран.", reply_markup=main_menu_kb())
    await state.clear()


@router.message(BudgetStates.waiting_global_limit)
async def step_global_limit(message: Message, state: FSMContext) -> None:
    try:
        amount = float(message.text.replace(",", ".").replace(" ", ""))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи положительное число:")
        return
    await set_monthly_limit(message.from_user.id, amount)
    await message.answer(
        f"✅ Общий лимит <b>{fmt_amount(amount)}/мес</b> установлен!",
        reply_markup=main_menu_kb(),
    )
    await state.clear()
