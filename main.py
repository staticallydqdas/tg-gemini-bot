import asyncio
import hashlib
import html
import logging
import os
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineQueryResultArticle, InputTextMessageContent
from google import genai

logging.getLogger("google.genai").setLevel(logging.ERROR)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
ai_client = genai.Client(api_key=GEMINI_API_KEY)

def ask_gemini(text: str) -> str:
    for model_name in ["gemini-3.5-flash-lite", "gemini-3.6-flash"]:
        try:
            response = ai_client.models.generate_content(
                model=model_name,
                contents=text,
                config={
                    "system_instruction": "Отвечай максимально емко и кратко, 1-2 предложения.",
                    "max_output_tokens": 100,
                },
            )
            if response.text:
                return response.text.strip()
        except Exception as e:
            print(f"Ошибка {model_name}: {e}")
            continue
    return "Не удалось получить ответ, попробуйте позже."

# Ответ в ЛС
@dp.message()
async def message_handler(message: types.Message):
    if not message.text:
        return
    status_msg = await message.reply("⏳ Генерирую ответ...")
    answer = await asyncio.to_thread(ask_gemini, message.text.strip())
    await status_msg.edit_text(answer)

# Инлайн: генерация ответа на лету прямо в превью карточки
@dp.inline_query()
async def inline_handler(query: types.InlineQuery):
    text = query.query.strip()
    # Ждем ввода минимум 3 символов, чтобы не тратить квоту на обрывки слов
    if len(text) < 3:
        return

    # Запрашиваем Gemini сразу:
    answer = await asyncio.to_thread(ask_gemini, text)

    escaped_q = html.escape(text)
    escaped_a = html.escape(answer)
    q_id = hashlib.md5(text.encode("utf-8")).hexdigest()

    item = InlineQueryResultArticle(
        id=q_id,
        title=f"Ответ: {answer[:45]}...",
        description=answer[:80],
        input_message_content=InputTextMessageContent(
            message_text=f"❓ <b>{escaped_q}</b>\n\n{escaped_a}",
            parse_mode="HTML"
        )
    )

    # cache_time=300 сохраняет ответ на 5 минут для одинаковых вопросов (экономит квоту)
    await query.answer([item], cache_time=300, is_personal=True)

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await asyncio.sleep(1)
    print("Бот готов к работе!")
    await dp.start_polling(bot, allowed_updates=["message", "inline_query"])

if __name__ == "__main__":
    asyncio.run(main())
