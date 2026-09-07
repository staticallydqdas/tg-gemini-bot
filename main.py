import asyncio
import hashlib
import html
import os
import traceback
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineQueryResultArticle, InputTextMessageContent
from google import genai

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# Инициализируем клиент Gemini
ai_client = genai.Client(api_key=GEMINI_API_KEY)

@dp.inline_query()
async def inline_handler(query: types.InlineQuery):
    text = query.query.strip()
    
    # Не запрашиваем API, пока набрано меньше 2 символов
    if len(text) < 2:
        return

    print(f"Получен запрос: {text}")

    try:
        # Запрос к модели
        response = ai_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=text
        )
        answer = response.text or "Не удалось сформировать ответ."
        print(f"Успешный ответ от Gemini (длина: {len(answer)})")

        query_id = hashlib.md5(text.encode("utf-8")).hexdigest()

        # Экранируем спецсимволы, чтобы Telegram не падал из-за разметки
        safe_q = html.escape(text)
        safe_a = html.escape(answer)

        item = InlineQueryResultArticle(
            id=query_id,
            title="Ответ нейросети:",
            description=answer[:70] + "...",
            input_message_content=InputTextMessageContent(
                message_text=f"❓ <b>Вопрос:</b> {safe_q}\n\n💡 <b>Ответ:</b>\n{safe_a}",
                parse_mode="HTML"
            )
        )

        await query.answer([item], cache_time=3, is_personal=True)

    except Exception as e:
        print(f"ОШИБКА при обработке запроса: {e}")
        traceback.print_exc()

async def main():
    print("Бот успешно запущен и слушает Telegram...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
