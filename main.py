import asyncio
import hashlib
import html
import logging
import os
import traceback
from aiogram import Bot, Dispatcher, types
from aiogram.types import (
    InlineQueryResultArticle,
    InputTextMessageContent,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from google import genai

logging.getLogger("google.genai").setLevel(logging.ERROR)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
ai_client = genai.Client(api_key=GEMINI_API_KEY)

# Хранилище запросов, чтобы бот помнил, о чем вопрос
cache_prompts = {}

def ask_gemini(text: str) -> str:
    for model_name in ["gemini-3.5-flash-lite", "gemini-3.6-flash"]:
        try:
            response = ai_client.models.generate_content(
                model=model_name,
                contents=text,
                config={
                    "system_instruction": "Отвечай кратко, емко, не более 2 предложений.",
                    "max_output_tokens": 120,
                },
            )
            if response.text:
                return response.text.strip()
        except Exception as e:
            print(f"Ошибка {model_name}: {e}")
            continue
    return "Не удалось получить ответ, попробуйте позже."

@dp.message()
async def message_handler(message: types.Message):
    if not message.text:
        return
    status_msg = await message.reply("⏳ Генерирую ответ...")
    answer = await asyncio.to_thread(ask_gemini, message.text.strip())
    await status_msg.edit_text(answer)

@dp.inline_query()
async def inline_handler(query: types.InlineQuery):
    text = query.query.strip()
    if len(text) < 2:
        return

    q_id = hashlib.md5(text.encode("utf-8")).hexdigest()[:16]
    cache_prompts[q_id] = text
    escaped_q = html.escape(text)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏳ Получить ответ...", callback_data=f"ai:{q_id}")]
        ]
    )

    item = InlineQueryResultArticle(
        id=q_id,
        title=f"Спросить: {text[:50]}",
        description="Отправить в чат и получить ответ ИИ",
        input_message_content=InputTextMessageContent(
            message_text=f"❓ <b>{escaped_q}</b>\n\n<i>⏳ Нейросеть генерирует ответ...</i>",
            parse_mode="HTML",
        ),
        reply_markup=kb,
    )
    await query.answer([item], cache_time=0, is_personal=True)

# Функция редактирования сообщения в чате
async def update_inline(inline_msg_id: str, prompt: str):
    escaped_q = html.escape(prompt)
    try:
        answer = await asyncio.to_thread(ask_gemini, prompt)
        escaped_a = html.escape(answer)
        await bot.edit_message_text(
            inline_message_id=inline_msg_id,
            text=f"❓ <b>{escaped_q}</b>\n\n{escaped_a}",
            parse_mode="HTML",
            reply_markup=None,
        )
        print(f"<- Сообщение успешно обновлено: {prompt[:30]}")
    except Exception as e:
        print(f"Ошибка обновления: {e}")
        traceback.print_exc()

# 1. Автоматический вариант (если Telegram передал chosen_inline_result)
@dp.chosen_inline_result()
async def on_chosen_inline_result(chosen_result: types.ChosenInlineResult):
    text = chosen_result.query.strip()
    print(f"-> Telegram прислал chosen_inline: {text}")
    if chosen_result.inline_message_id:
        asyncio.create_task(update_inline(chosen_result.inline_message_id, text))

# 2. Мгновенный ручной вариант по клику на кнопку (если chosen_inline не пришел)
@dp.callback_query(lambda c: c.data and c.data.startswith("ai:"))
async def on_click(callback: types.CallbackQuery):
    await callback.answer("⏳ Генерирую...")
    q_id = callback.data.split(":")[1]
    prompt = cache_prompts.get(q_id, "Запрос")
    if callback.inline_message_id:
        asyncio.create_task(update_inline(callback.inline_message_id, prompt))

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await asyncio.sleep(1)
    print("Бот готов к работе!")
    await dp.start_polling(
        bot,
        allowed_updates=["message", "inline_query", "chosen_inline_result", "callback_query"],
    )

if __name__ == "__main__":
    asyncio.run(main())
