"""
handlers/categories.py — управление категориями (список, добавить, удалить).
"""

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from database.queries import get_categories, add_category, delete_category
from keyboards.main_menu import main_menu_kb
from keyboards.categories import manage_categories_kb

router = Router(name="categories")

ICONS = ["🍔","🚗","🏠","💊","🎮","👗","📚","🛒","☕","📱","💡","🎁","✈️","🐾",
         "💼","📈","🎰","💸","🏋️","🎵","🍕","🎬","📦","🌿","🐶","💻","🏖️","❓"]
COLORS = ["#e74c3c","#e67e22","#8e44ad","#27ae60","#2980b9","#e91e63",
          "#16a085","#d35400","#795548","#607d8b","#f39c12","#9c27b0",
          "#00bcd4","#8bc34a","#95a5a6"]


class CatStates(StatesGroup):
    waiting_name = State()
    waiting_icon = State()
    waiting_type = State()


@router.callback_query(F.data == "categories")
@router.message(Command("categories"))
async def show_categories(event, state=None) -> None:
    msg = event if isinstance(event, Message) else event.message
    user_id = event.from_user.id

    exp_cats = await get_categories(user_id, is_income=False)
    inc_cats = await get_categories(user_id, is_income=True)

    lines = ["🗂 <b>Категории расходов:</b>\n"]
    for c in exp_cats:
        lines.append(f"  {c['icon']} {c['name']}")
    lines.append("\n💚 <b>Категории доходов:</b>\n")
    for c in inc_cats:
        lines.append(f"  {c['icon']} {c['name']}")

    text = "\n".join(lines)

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=manage_categories_kb())
        await event.answer()
    else:
        await msg.answer(text, reply_markup=manage_categories_kb())


@router.callback_query(F.data == "add_category")
async def cb_add_category(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_text(
        "➕ <b>Новая категория</b>\n\n"
        "Введи название категории:"
    )
    await state.set_state(CatStates.waiting_name)
    await callback.answer()


@router.message(CatStates.waiting_name)
async def step_cat_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=message.text.strip())
    icons_str = "  ".join(ICONS)
    await message.answer(
        f"Выбери иконку для категории:\n\n{icons_str}\n\n"
        "Напиши один эмодзи:"
    )
    await state.set_state(CatStates.waiting_icon)


@router.message(CatStates.waiting_icon)
async def step_cat_icon(message: Message, state: FSMContext) -> None:
    icon = message.text.strip()
    await state.update_data(icon=icon if icon else "❓")
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💸 Расход", callback_data="cat_type:0"),
            InlineKeyboardButton(text="💚 Доход",  callback_data="cat_type:1"),
        ]
    ])
    await message.answer("Тип категории:", reply_markup=kb)
    await state.set_state(CatStates.waiting_type)


@router.callback_query(CatStates.waiting_type, F.data.startswith("cat_type:"))
async def step_cat_type(callback: CallbackQuery, state: FSMContext) -> None:
    is_income = bool(int(callback.data.split(":")[1]))
    data = await state.get_data()
    import random
    color = random.choice(COLORS)

    cat_id = await add_category(
        user_id=callback.from_user.id,
        name=data["name"],
        icon=data["icon"],
        color=color,
        is_income=is_income,
    )
    if cat_id:
        await callback.message.edit_text(
            f"✅ Категория <b>{data['icon']} {data['name']}</b> добавлена!",
            reply_markup=main_menu_kb(),
        )
    else:
        await callback.message.edit_text(
            "❌ Такая категория уже существует.", reply_markup=main_menu_kb()
        )
    await state.clear()
    await callback.answer()


@router.callback_query(F.data.startswith("del_cat:"))
async def cb_delete_cat(callback: CallbackQuery) -> None:
    cat_id = int(callback.data.split(":")[1])
    ok = await delete_category(cat_id, callback.from_user.id)
    if ok:
        await callback.answer("🗑 Категория удалена", show_alert=True)
    else:
        await callback.answer("❌ Системную категорию нельзя удалить", show_alert=True)
    await show_categories(callback)
