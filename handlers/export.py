"""
handlers/export.py — экспорт транзакций в Excel (.xlsx).

"""

import logging
from datetime import datetime

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, BufferedInputFile
from aiogram.exceptions import TelegramBadRequest

from config import settings
from database.queries import get_all_transactions_for_export
from keyboards.main_menu import main_menu_kb
from services.excel_export import generate_excel_report

logger = logging.getLogger(__name__)
router = Router(name="export")


@router.callback_query(F.data.startswith("export_month:"))
async def cb_export_month(callback: CallbackQuery) -> None:
    parts      = callback.data.split(":")
    year, month = int(parts[1]), int(parts[2])
    user_id    = callback.from_user.id

    await callback.answer("⏳ Генерирую Excel файл...")

    try:
        transactions = await get_all_transactions_for_export(user_id)
        if not transactions:
            await callback.message.answer("📭 Нет данных для экспорта.", reply_markup=main_menu_kb())
            return

        xlsx_bytes = generate_excel_report(
            transactions=transactions,
            year=year,
            month=month,
            currency=settings.DEFAULT_CURRENCY,
        )

        MONTHS = ["","Январь","Февраль","Март","Апрель","Май","Июнь",
                  "Июль","Август","Сентябрь","Октябрь","Ноябрь","Декабрь"]
        filename = f"finance_{year}_{month:02d}.xlsx"

        await callback.message.answer_document(
            BufferedInputFile(xlsx_bytes, filename=filename),
            caption=(
                f"📊 <b>Отчёт за {MONTHS[month]} {year}</b>\n\n"
                f"📋 Лист 1: Все транзакции\n"
                f"📋 Лист 2: Расходы по категориям\n"
                f"📋 Лист 3: Итоги по месяцам\n\n"
                f"<i>Открой в LibreOffice Calc двойным кликом</i>"
            ),
            reply_markup=main_menu_kb(),
        )

    except Exception as e:
        logger.error("Excel export error: %s", e)
        await callback.message.answer(
            "❌ Ошибка при генерации файла. Попробуй позже.",
            reply_markup=main_menu_kb(),
        )


@router.callback_query(F.data.startswith("export_year:"))
async def cb_export_year(callback: CallbackQuery) -> None:
    year    = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    await callback.answer("⏳ Генерирую Excel файл...")

    try:
        transactions = await get_all_transactions_for_export(user_id)
        if not transactions:
            await callback.message.answer("📭 Нет данных для экспорта.", reply_markup=main_menu_kb())
            return

        xlsx_bytes = generate_excel_report(
            transactions=transactions,
            year=year,
            month=None,
            currency=settings.DEFAULT_CURRENCY,
        )

        filename = f"finance_{year}.xlsx"

        await callback.message.answer_document(
            BufferedInputFile(xlsx_bytes, filename=filename),
            caption=(
                f"📊 <b>Годовой отчёт {year}</b>\n\n"
                f"📋 Лист 1: Все транзакции\n"
                f"📋 Лист 2: Расходы по категориям\n"
                f"📋 Лист 3: Итоги по месяцам\n\n"
                f"<i>Открой в LibreOffice Calc двойным кликом</i>"
            ),
            reply_markup=main_menu_kb(),
        )

    except Exception as e:
        logger.error("Excel export year error: %s", e)
        await callback.message.answer(
            "❌ Ошибка при генерации файла. Попробуй позже.",
            reply_markup=main_menu_kb(),
        )


@router.message(Command("export"))
async def cmd_export(message: Message) -> None:
    now = datetime.now()
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"📥 Excel за {now.month:02d}.{now.year}",
                callback_data=f"export_month:{now.year}:{now.month}"
            ),
        ],
        [
            InlineKeyboardButton(
                text=f"📥 Excel за {now.year} год",
                callback_data=f"export_year:{now.year}"
            ),
        ],
        [InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu")],
    ])
    await message.answer("📥 <b>Экспорт в Excel</b>\n\nВыбери период:", reply_markup=kb)