"""
handlers/voice.py — обработка голосовых сообщений через Groq Whisper API.

Groq предоставляет бесплатный API с моделью whisper-large-v3.
Регистрация: https://console.groq.com
"""

import os
import tempfile
import logging

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, Voice

from config import settings
from handlers.expenses import ExpenseStates
from utils.parser import parse_expense_text
from utils.formatters import fmt_amount
from keyboards.categories import categories_kb
from database.queries import get_categories

logger = logging.getLogger(__name__)
router = Router(name="voice")


async def transcribe_with_groq(bot: Bot, voice: Voice) -> str | None:
    """Транскрибирует голосовое через Groq Whisper API."""
    groq_key = getattr(settings, "GROQ_API_KEY", "") or os.getenv("GROQ_API_KEY", "")
    if not groq_key:
        return None

    try:
        from groq import Groq

        # Скачиваем OGG файл
        file_info = await bot.get_file(voice.file_id)
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp_path = tmp.name
        await bot.download_file(file_info.file_path, destination=tmp_path)

        # Отправляем в Groq
        client = Groq(api_key=groq_key)
        with open(tmp_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                file=("voice.ogg", audio_file.read()),
                model="whisper-large-v3",
                language="ru",
                response_format="text",
            )
        os.unlink(tmp_path)
        return transcription.strip() if transcription else None

    except Exception as e:
        logger.error("Groq transcription error: %s", e)
        return None


@router.message(F.voice)
async def handle_voice(message: Message, state: FSMContext, bot: Bot) -> None:
    groq_key = getattr(settings, "GROQ_API_KEY", "") or os.getenv("GROQ_API_KEY", "")

    if not groq_key:
        await message.answer(
            "🎙 Голосовой ввод недоступен.\n\n"
            "Для активации:\n"
            "1. Зарегистрируйся на <b>console.groq.com</b>\n"
            "2. Получи бесплатный API ключ\n"
            "3. Добавь в .env: <code>GROQ_API_KEY=gsk_...</code>\n\n"
            "Введи расход текстом: <code>кофе 150</code>"
        )
        return

    processing_msg = await message.answer("🎙 Распознаю голосовое...")

    text = await transcribe_with_groq(bot, message.voice)

    if not text:
        await processing_msg.edit_text(
            "❌ Не удалось распознать речь.\n"
            "Попробуй говорить чётче или введи текстом."
        )
        return

    await processing_msg.edit_text(f"🎙 Распознано: <i>«{text}»</i>")

    parsed = parse_expense_text(text)
    if not parsed:
        await message.answer(
            f"❓ Не нашёл сумму в: <i>«{text}»</i>\n\n"
            "Попробуй: <code>потратил 500 на обед</code>"
        )
        return

    await state.update_data(
        amount=parsed["amount"],
        note=parsed.get("note") or text,
        source="voice",
    )

    categories = await get_categories(message.from_user.id, is_income=False)
    await message.answer(
        f"✅ Распознано!\n"
        f"💸 Сумма: <b>{fmt_amount(parsed['amount'])}</b>\n"
        f"📝 Описание: <i>{parsed.get('note') or text}</i>\n\n"
        "Выбери категорию:",
        reply_markup=categories_kb(categories, prefix="exp_cat"),
    )
    await state.set_state(ExpenseStates.waiting_category)
