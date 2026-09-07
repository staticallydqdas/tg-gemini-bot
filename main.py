import asyncio
import hashlib
import html
import io
import logging
import os
from collections import defaultdict
from aiogram import Bot, Dispatcher, F, types
from aiogram.types import InlineQueryResultArticle, InputTextMessageContent
from google import genai
from google.genai import types as genai_types

logging.getLogger("google.genai").setLevel(logging.ERROR)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
ai_client = genai.Client(api_key=GEMINI_API_KEY)

# Контекстная память для личных сообщений (user_id -> список сообщений)
user_history = defaultdict(list)
MAX_HISTORY = 6

SYSTEM_PROMPT = (
    "Ты — полезный, умный и лаконичный ИИ-ассистент. "
    "Отвечай емко, по делу, с четкой структурой (используй списки и выделение жирным ключевых понятий). "
    "Никакой воды, шаблонных вежливых вступлений или затянутых выводов. Сразу к сути вопроса."
)

def query_gemini_multimodal(contents: list, use_search: bool = False) -> str:
    """Универсальный вызов Gemini для текста, медиа и поиска."""
    tools = []
    if use_search:
        # Включаем встроенный поиск Google в реальном времени
        tools.append(genai_types.Tool(google_search=genai_types.GoogleSearch()))

    config = genai_types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        temperature=0.3,
        max_output_tokens=1000,
        tools=tools if tools else None,
    )

    for model_name in ["gemini-3.5-flash-lite", "gemini-3.6-flash"]:
        try:
            response = ai_client.models.generate_content(
                model=model_name,
                contents=contents,
                config=config,
            )
            if response.text:
                return response.text.strip()
        except Exception as e:
            print(f"Ошибка вызова {model_name}: {e}")
            continue
    return "Не удалось получить ответ от нейросети. Попробуйте чуть позже."

# 1. Сброс истории диалога
@dp.message(F.text == "/reset")
async def reset_context(message: types.Message):
    user_history[message.from_user.id].clear()
    await message.reply("🧹 История диалога очищена. Можем начать с чистого листа!")

# 2. Обработка текстовых сообщений в ЛС (с контекстной памятью и поиском)
@dp.message(F.text)
async def text_handler(message: types.Message):
    user_id = message.from_user.id
    user_text = message.text.strip()

    status_msg = await message.reply("⏳ Изучаю вопрос...")

    # Сохраняем запрос в историю
    user_history[user_id].append({"role": "user", "parts": [{"text": user_text}]})
    if len(user_history[user_id]) > MAX_HISTORY:
        user_history[user_id] = user_history[user_id][-MAX_HISTORY:]

    # Собираем контекст сообщений
    contents = []
    for turn in user_history[user_id]:
        contents.append(genai_types.Content(
            role=turn["role"],
            parts=[genai_types.Part.from_text(text=turn["parts"][0]["text"])]
        ))

    # Gemini сама решит, нужен ли Google Search (например, для курсов, новостей, дат)
    answer = await asyncio.to_thread(query_gemini_multimodal, contents, True)

    # Сохраняем ответ модели в историю
    user_history[user_id].append({"role": "model", "parts": [{"text": answer}]})

    # Если ответ длинный, делим на части для лимита Telegram (4096 символов)
    for i in range(0, len(answer), 4000):
        chunk = answer[i:i+4000]
        if i == 0:
            await status_msg.edit_text(chunk)
        else:
            await message.answer(chunk)

# 3. Анализ фотографий и картинок
@dp.message(F.photo)
async def photo_handler(message: types.Message):
    status_msg = await message.reply("🔍 Анализирую изображение...")
    photo = message.photo[-1]
    file_io = io.BytesIO()
    await bot.download(photo, destination=file_io)
    image_bytes = file_io.getvalue()

    caption = message.caption.strip() if message.caption else "Что изображено на этой фотографии? Опиши подробно и по делу."

    contents = [
        genai_types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
        genai_types.Part.from_text(text=caption),
    ]

    answer = await asyncio.to_thread(query_gemini_multimodal, contents, False)
    await status_msg.edit_text(answer)

# 4. Распознавание голосовых сообщений (Voice)
@dp.message(F.voice)
async def voice_handler(message: types.Message):
    status_msg = await message.reply("🎙 Слушаю голосовое сообщение...")
    file_io = io.BytesIO()
    await bot.download(message.voice, destination=file_io)
    voice_bytes = file_io.getvalue()

    contents = [
        genai_types.Part.from_bytes(data=voice_bytes, mime_type="audio/ogg"),
        genai_types.Part.from_text(
            text="Расшифруй это голосовое сообщение и дай четкий ответ или выжимку на то, о чем в нем говорится."
        ),
    ]

    answer = await asyncio.to_thread(query_gemini_multimodal, contents, True)
    await status_msg.edit_text(answer)

# 5. Инлайн-режим для вызова в любых внешних чатах
@dp.inline_query()
async def inline_handler(query: types.InlineQuery):
    text = query.query.strip()
    if len(text) < 2:
        return

    contents = [genai_types.Part.from_text(text=text)]
    answer = await asyncio.to_thread(query_gemini_multimodal, contents, True)

    escaped_q = html.escape(text)
    escaped_a = html.escape(answer)
    q_id = hashlib.md5(text.encode("utf-8")).hexdigest()

    item = InlineQueryResultArticle(
        id=q_id,
        title=f"💡 Задать вопрос: {text[:40]}",
        description=answer[:80],
        input_message_content=InputTextMessageContent(
            message_text=f"❓ <b>{escaped_q}</b>\n\n{escaped_a}",
            parse_mode="HTML",
        ),
    )
    await query.answer([item], cache_time=180, is_personal=True)

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await asyncio.sleep(1)
    print("Бот готов к работе с мультимодальностью, поиском и инлайном!")
    await dp.start_polling(bot, allowed_updates=["message", "inline_query"])

if __name__ == "__main__":
    asyncio.run(main())
