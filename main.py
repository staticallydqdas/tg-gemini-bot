import asyncio
import hashlib
import html
import io
import logging
import os
import random
import urllib.parse
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

# Настройка дерзкого тона с матом
SYSTEM_INSTRUCTION = (
    "Ты — дерзкий, остроумный, прямолинейный ИИ-собеседник. "
    "Используй русский мат органично, к месту, для экспрессии, сарказма и колорита. "
    "Отвечай емко, по существу, с юмором или иронией, без лишней воды и шаблонной занудной вежливости. "
    "Без прямой необоснованной агрессии на пользователя, но с хорошей порцией дерзости."
)

# Отключение цензуры
SAFETY_SETTINGS = [
    genai_types.SafetySetting(
        category=genai_types.HarmCategory.HARM_CATEGORY_HARASSMENT,
        threshold=genai_types.HarmBlockThreshold.BLOCK_NONE,
    ),
    genai_types.SafetySetting(
        category=genai_types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        threshold=genai_types.HarmBlockThreshold.BLOCK_NONE,
    ),
]

def ask_gemini(prompt: str) -> str:
    """Генерация текста с отключенными фильтрами цензуры."""
    for model_name in ["gemini-2.5-flash", "gemini-2.0-flash"]:
        try:
            response = ai_client.models.generate_content(
                model=model_name,
                contents=prompt,
                config={
                    "system_instruction": SYSTEM_INSTRUCTION,
                    "max_output_tokens": 800,
                    "temperature": 0.85,
                    "safety_settings": SAFETY_SETTINGS,
                },
            )
            if response.text:
                return response.text.strip()
        except Exception as e:
            print(f"Ошибка {model_name}: {e}", flush=True)
            continue
    return "Чё-то пошло по п**де, попробуй чуть позже."

def translate_prompt_to_en(ru_prompt: str) -> str:
    """Перевод и адаптация для генератора картинок."""
    try:
        res = ai_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"Translate this image prompt into a detailed English prompt for text-to-image AI: {ru_prompt}. Output ONLY the prompt in English.",
            config={"max_output_tokens": 80, "temperature": 0.2}
        )
        if res.text:
            return res.text.strip().replace("\n", " ")
    except Exception as e:
        print(f"Ошибка перевода промпта: {e}", flush=True)
    return ru_prompt

# 1. Сброс / Старт
@dp.message(F.text.in_({"/start", "/reset"}))
async def cmd_start(message: types.Message):
    await message.reply("Здорово. Задавай вопросы, кидай скрины или зови меня через инлайн в чаты. Без цензуры.")

# 2. Текстовые сообщения в ЛС
@dp.message(F.text)
async def message_handler(message: types.Message):
    text = message.text.strip()
    status_msg = await message.reply("⏳ Ща соображу...")
    answer = await asyncio.to_thread(ask_gemini, text)
    await status_msg.edit_text(answer)

# 3. Фотографии в ЛС (анализ изображений)
@dp.message(F.photo)
async def photo_handler(message: types.Message):
    status_msg = await message.reply("🔍 Гляжу чё там...")
    photo = message.photo[-1]
    file_io = io.BytesIO()
    await bot.download(photo, destination=file_io)
    image_bytes = file_io.getvalue()

    caption = message.caption.strip() if message.caption else "Чё тут вообще происходит на картинке?"

    try:
        response = await asyncio.to_thread(
            ai_client.models.generate_content,
            model="gemini-2.5-flash",
            contents=[
                {"inline_data": {"mime_type": "image/jpeg", "data": image_bytes}},
                caption,
            ],
            config={
                "system_instruction": SYSTEM_INSTRUCTION,
                "safety_settings": SAFETY_SETTINGS,
            }
        )
        await status_msg.edit_text(response.text if response.text else "Не разобрал этот пиксельный ужас.")
    except Exception as e:
        print(f"Ошибка фото: {e}", flush=True)
        await status_msg.edit_text("Не удалось прочесть картинку, косяк какой-то.")

# 4. Инлайн-режим (картинки и тексты)
@dp.inline_query()
async def inline_handler(query: types.InlineQuery):
    text = query.query.strip()
    if len(text) < 2:
        return

    lower = text.lower()

    # Генерация картинок
    if any(lower.startswith(prefix) for prefix in ["нарисуй", "фото", "картинка", "draw"]):
        clean_prompt = text
        for p in ["нарисуй", "фото", "картинка", "draw"]:
            if lower.startswith(p):
                clean_prompt = text[len(p):].strip()
                break

        en_prompt = await asyncio.to_thread(translate_prompt_to_en, clean_prompt)
        seed = random.randint(1, 999999)
        encoded = urllib.parse.quote(en_prompt)
        image_url = f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&seed={seed}&nologo=true"

        q_id = hashlib.md5(f"{text}_{seed}".encode("utf-8")).hexdigest()

        item = InlineQueryResultPhoto(
            id=q_id,
            photo_url=image_url,
            thumbnail_url=image_url,
            caption=f"🎨 <b>Запрос:</b> {html.escape(clean_prompt)}",
            parse_mode="HTML",
        )
        await query.answer([item], cache_time=0, is_personal=True)
        return

    # Текстовые ответы
    q_id = hashlib.md5(text.encode("utf-8")).hexdigest()
    answer = await asyncio.to_thread(ask_gemini, text)
    escaped_q = html.escape(text)
    escaped_a = html.escape(answer)

    item = InlineQueryResultArticle(
        id=q_id,
        title=f"Ответ: {text[:35]}",
        description=answer[:80],
        input_message_content=InputTextMessageContent(
            message_text=f"❓ <b>{escaped_q}</b>\n\n{escaped_a}",
            parse_mode="HTML",
        ),
    )
    await query.answer([item], cache_time=30, is_personal=True)

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await asyncio.sleep(1)
    print("Бот дерзко запущен!", flush=True)
    await dp.start_polling(bot, allowed_updates=["message", "inline_query"])

if __name__ == "__main__":
    asyncio.run(main())
