"""
handlers/voice.py — обработка голосовых сообщений.

Pipeline:
  1. Получить voice → скачать OGG
  2. Отправить в OpenAI Whisper → получить транскрипт
  3. Распарсить сумму и заметку из текста
  4. Передать управление в expenses/income FSM
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


async def transcribe_voice(bot: Bot, voice: Voice) -> str | None:
    """Скачивает голосовое и транскрибирует через Whisper API."""
    if not settings.OPENAI_API_KEY:
        return None

    try:
        import openai
        client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        # Скачать файл во временную директорию
        file_info = await bot.get_file(voice.file_id)
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp_path = tmp.name

        await bot.download_file(file_info.file_path, destination=tmp_path)

        with open(tmp_path, "rb") as audio_file:
            transcript = await client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="ru",
            )
        os.unlink(tmp_path)
        return transcript.text

    except Exception as e:
        logger.error("Whisper transcription error: %s", e)
        return None


@router.message(F.voice)
async def handle_voice(message: Message, state: FSMContext, bot: Bot) -> None:
    processing_msg = await message.answer("🎙 Обрабатываю голосовое сообщение...")

    if not settings.OPENAI_API_KEY:
        await processing_msg.edit_text(
            "⚠️ <b>Голосовой ввод недоступен</b>\n\n"
            "Для активации добавь <code>OPENAI_API_KEY</code> в .env\n\n"
            "Введи расход текстом: <code>кофе 150</code>"
        )
        return

    text = await transcribe_voice(bot, message.voice)

    if not text:
        await processing_msg.edit_text(
            "❌ Не удалось распознать речь. Попробуй ещё раз или введи текстом."
        )
        return

    await processing_msg.edit_text(f'🎙 Распознано: <i>«{text}»</i>')

    parsed = parse_expense_text(text)
    if not parsed:
        await message.answer(
            f"❓ Не нашёл сумму в: <i>«{text}»</i>\n\n"
            "Попробуй формат: <code>потратил 500 на обед</code>"
        )
        return

    # Сохраняем в FSM и запрашиваем категорию
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
