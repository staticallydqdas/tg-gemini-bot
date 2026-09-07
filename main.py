import asyncio
import hashlib
import html
import io
import logging
import os
import urllib.parse
from collections import defaultdict
from aiogram import Bot, Dispatcher, F, types
from aiogram.types import (
    InlineQueryResultArticle,
    InlineQueryResultPhoto,
    InputTextMessageContent,
)
from google import genai
from google.genai import types as genai_types

logging.getLogger("google.genai").setLevel(logging.ERROR)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
ai_client = genai.Client(api_key=GEMINI_API_KEY)

user_history = defaultdict(list)
MAX_HISTORY = 6

SYSTEM_PROMPT = (
    "Ты — полезный, умный и лаконичный ИИ-ассистент. "
    "Отвечай емко, по делу, с четкой структурой. "
    "Никакой воды и шаблонных вежливых вступлений. Сразу к сути."
)

def ask_gemini(contents: list) -> str:
    """Стабильный вызов Gemini без блокировок поиска."""
    config = genai_types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        temperature=0.3,
        max_output_tokens=800,
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
            print(f"Ошибка {model_name}: {e}")
            continue
    return "Не удалось получить ответ, попробуйте позже."

# 1. Очистка контекста
@dp.message(F.text == "/reset")
async def reset_context(message: types.Message):
    user_history[message.from_user.id].clear()
    await message.reply("🧹 История очищена!")

# 2. Текстовые сообщения в ЛС
@dp.message(F.text)
async def text_handler(message: types.Message):
    user_id = message.from_user.id
    user_text = message.text.strip()

    status_msg = await message.reply("⏳ Думаю...")

    user_history[user_id].append({"role": "user", "text": user_text})
    if len(user_history[user_id]) > MAX_HISTORY:
        user_history[user_id] = user_history[user_id][-MAX_HISTORY:]

    contents = [
        genai_types.Content(
            role=turn["role"],
            parts=[genai_types.Part.from_text(text=turn["text"])]
        )
        for turn in user_history[user_id]
    ]

    answer = await asyncio.to_thread(ask_gemini, contents)
    user_history[user_id].append({"role": "model", "text": answer})

    for i in range(0, len(answer), 4000):
        chunk = answer[i:i+4000]
        if i == 0:
            await status_msg.edit_text(chunk)
        else:
            await message.answer(chunk)

# 3. Фотографии в ЛС
@dp.message(F.photo)
async def photo_handler(message: types.Message):
    status_msg = await message.reply("🔍 Анализирую изображение...")
    photo = message.photo[-1]
    file_io = io.BytesIO()
    await bot.download(photo, destination=file_io)
    image_bytes = file_io.getvalue()

    caption = message.caption.strip() if message.caption else "Опиши подробно, что на этой фотографии."
    contents = [
        genai_types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
        genai_types.Part.from_text(text=caption),
    ]

    answer = await asyncio.to_thread(ask_gemini, contents)
    await status_msg.edit_text(answer)

# 4. Голосовые сообщения в ЛС
@dp.message(F.voice)
async def voice_handler(message: types.Message):
    status_msg = await message.reply("🎙 Слушаю голосовое...")
    file_io = io.BytesIO()
    await bot.download(message.voice, destination=file_io)
    voice_bytes = file_io.getvalue()

    contents = [
        genai_types.Part.from_bytes(data=voice_bytes, mime_type="audio/ogg"),
        genai_types.Part.from_text(text="Расшифруй это голосовое и дай краткий ответ на то, что там сказано."),
    ]

    answer = await asyncio.to_thread(ask_gemini, contents)
    await status_msg.edit_text(answer)

# 5. Инлайн-режим: Умное разделение на текст и генерацию картинок
@dp.inline_query()
async def inline_handler(query: types.InlineQuery):
    text = query.query.strip()
    if len(text) < 2:
        return

    q_id = hashlib.md5(text.encode("utf-8")).hexdigest()
    lower_text = text.lower()

    # Если запрос начинается со слов про рисование:
    if lower_text.startswith(("нарисуй", "картинка", "фото", "draw", "image")):
        prompt = text
        for trigger in ["нарисуй", "картинка", "фото"]:
            if lower_text.startswith(trigger):
                prompt = text[len(trigger):].strip()
                break

        encoded_prompt = urllib.parse.quote(prompt)
        image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true"

        item = InlineQueryResultPhoto(
            id=q_id,
            photo_url=image_url,
            thumbnail_url=image_url,
            caption=f"🎨 <b>Запрос:</b> {html.escape(prompt)}",
            parse_mode="HTML",
        )
        await query.answer([item], cache_time=60, is_personal=True)
        return

    # Обычный текстовый запрос к Gemini
    contents = [genai_types.Part.from_text(text=text)]
    answer = await asyncio.to_thread(ask_gemini, contents)

    escaped_q = html.escape(text)
    escaped_a = html.escape(answer)

    item = InlineQueryResultArticle(
        id=q_id,
        title=f"✨ Ответ на: {text[:40]}",
        description=answer[:80],
        input_message_content=InputTextMessageContent(
            message_text=f"❓ <b>{escaped_q}</b>\n\n{escaped_a}",
            parse_mode="HTML",
        ),
    )
    await query.answer([item], cache_time=120, is_personal=True)

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await asyncio.sleep(1)
    print("Бот успешно запущен!")
    await dp.start_polling(bot, allowed_updates=["message", "inline_query"])

if __name__ == "__main__":
    asyncio.run(main())
