import asyncio
import hashlib
import os
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineQueryResultArticle, InputTextMessageContent
from google import genai

# Токены берем из переменных окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
ai_client = genai.Client(api_key=GEMINI_API_KEY)

@dp.inline_query()
async def inline_handler(query: types.InlineQuery):
    text = query.query.strip()
    
    # Не дергаем API, если запрос слишком короткий
    if len(text) < 3:
        return

    try:
        # Используем быструю модель Flash для быстрого ответа во всплывающем окне
        response = ai_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=text,
            config={
                "system_instruction": "Отвечай кратко, тезисно и информативно, в формате удобного сообщения для чата."
            }
        )
        answer = response.text or "Не удалось сгенерировать ответ."

        query_id = hashlib.md5(text.encode()).hexdigest()

        # Формируем кликабельную плашку
        item = InlineQueryResultArticle(
            id=query_id,
            title="Ответ от Gemini:",
            description=answer[:80] + "...",
            input_message_content=InputTextMessageContent(
                message_text=f"💬 *Вопрос:* {text}\n\n💡 *Ответ:*\n{answer}",
                parse_mode="Markdown"
            )
        )

        await query.answer([item], cache_time=5, is_personal=True)

    except Exception as e:
        print(f"Error: {e}")

async def main():
    print("Бот успешно запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())