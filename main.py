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
ai_client = genai.Client(api_key=GEMINI_API_KEY)

def ask_gemini(text: str) -> str:
    response = ai_client.models.generate_content(
        model="gemini-3.6-flash",
        contents=f"Ответь кратко и емко (1-2 предложения): {text}"
    )
    return response.text or "Ответ не сформирован."

@dp.inline_query()
async def inline_handler(query: types.InlineQuery):
    text = query.query.strip()
    if len(text) < 2:
        return

    print(f"-> Запрос: {text}")

    try:
        # Выполняем в отдельном потоке, чтобы не подвешивать Telegram
        answer = await asyncio.to_thread(ask_gemini, text)
        print(f"<- Ответ готов ({len(answer)} симв.)")

        q_id = hashlib.md5(text.encode("utf-8")).hexdigest()
        escaped_q = html.escape(text)
        escaped_a = html.escape(answer)

        item = InlineQueryResultArticle(
            id=q_id,
            title="💡 Нажмите для отправки ответа:",
            description=answer[:80].replace("\n", " ") + "...",
            input_message_content=InputTextMessageContent(
                message_text=f"❓ <b>{escaped_q}</b>\n\n{escaped_a}",
                parse_mode="HTML"
            )
        )

        await query.answer([item], cache_time=2, is_personal=True)

    except Exception as e:
        print(f"ОШИБКА: {e}")
        traceback.print_exc()
        q_id = hashlib.md5(text.encode("utf-8")).hexdigest()
        err_item = InlineQueryResultArticle(
            id=q_id,
            title="Ошибка генерации",
            description=str(e)[:60],
            input_message_content=InputTextMessageContent(
                message_text=f"⚠️ Не удалось получить ответ: {e}"
            )
        )
        await query.answer([err_item], cache_time=1, is_personal=True)

async def main():
    print("Бот готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
