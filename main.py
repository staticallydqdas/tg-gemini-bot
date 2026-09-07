import asyncio
import hashlib
import html
import os
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineQueryResultArticle, InputTextMessageContent
from google import genai

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
ai_client = genai.Client(api_key=GEMINI_API_KEY)

@dp.inline_query()
async def inline_query_handler(query: types.InlineQuery):
    text = query.query.strip()
    if len(text) < 3:
        return

    try:
        # Запрашиваем ответ у Gemini
        response = ai_client.models.generate_content(
            model="gemini-3.6-flash",
            contents=text
        )
        answer = response.text or "Ответ не сформирован."

        q_id = hashlib.md5(text.encode("utf-8")).hexdigest()
        escaped_q = html.escape(text)
        escaped_a = html.escape(answer)

        # Карточка результата
        item = InlineQueryResultArticle(
            id=q_id,
            title="Отправить ответ в чат:",
            description=answer[:60] + "...",
            input_message_content=InputTextMessageContent(
                message_text=f"❓ <b>{escaped_q}</b>\n\n{escaped_a}",
                parse_mode="HTML"
            )
        )

        await query.answer([item], cache_time=1, is_personal=True)
    except Exception as e:
        print(f"Ошибка Gemini: {e}")

async def main():
    print("Бот слушает запросы...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
