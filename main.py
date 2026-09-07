import asyncio
import hashlib
import html
import logging
import os
import traceback
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
    for model_name in ["gemini-2.5-flash-lite", "gemini-2.5-flash"]:
        try:
            response = ai_client.models.generate_content(
                model=model_name,
                contents=text,
                config={
                    "system_instruction": "Отвечай кратко, емко, 1-2 предложения.",
                    "max_output_tokens": 150,
                }
            )
            if response.text:
                return response.text
        except Exception:
            continue
    return "Сервер временно перегружен, попробуйте чуть позже."

@dp.inline_query()
async def inline_handler(query: types.InlineQuery):
    text = query.query.strip()
    if len(text) < 2:
        return

    q_id = hashlib.md5(text.encode("utf-8")).hexdigest()
    escaped_q = html.escape(text)

    # Мгновенно отдаем плашку пользователю (0.01 сек), не дожидаясь ответа нейросети
    item = InlineQueryResultArticle(
        id=q_id,
        title="✨ Спросить нейросеть:",
        description=text[:60],
        input_message_content=InputTextMessageContent(
            message_text=f"❓ <b>{escaped_q}</b>\n\n<i>⏳ Нейросеть генерирует ответ...</i>",
            parse_mode="HTML"
        )
    )
    await query.answer([item], cache_time=1, is_personal=True)

@dp.chosen_inline_result()
async def on_chosen_inline_result(chosen_result: types.ChosenInlineResult):
    if not chosen_result.inline_message_id:
        return

    text = chosen_result.query.strip()
    escaped_q = html.escape(text)

    try:
        answer = await asyncio.to_thread(ask_gemini, text)
        escaped_a = html.escape(answer)
        await bot.edit_message_text(
            inline_message_id=chosen_result.inline_message_id,
            text=f"❓ <b>{escaped_q}</b>\n\n{escaped_a}",
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"Ошибка обновления сообщения: {e}")
        traceback.print_exc()

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await asyncio.sleep(1)
    print("Бот готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
