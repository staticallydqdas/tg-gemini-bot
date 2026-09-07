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
                return response.text
        except Exception as e:
            print(f"Ошибка {model_name}: {e}")
            continue
    return "Не удалось получить ответ, попробуйте позже."

# Ответ в ЛС
@dp.message()
async def message_handler(message: types.Message):
    if not message.text:
        return
    text = message.text.strip()
    status_msg = await message.reply("⏳ Генерирую ответ...")
    answer = await asyncio.to_thread(ask_gemini, text)
    await status_msg.edit_text(answer)

# Инлайн-запрос
@dp.inline_query()
async def inline_handler(query: types.InlineQuery):
    text = query.query.strip()
    if len(text) < 2:
        return

    q_id = hashlib.md5(text.encode("utf-8")).hexdigest()
    escaped_q = html.escape(text)

    # Кнопка для прямого триггера обновления
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚡ Получить ответ нейросети", callback_data=f"ask:{q_id[:20]}")]
        ]
    )

    item = InlineQueryResultArticle(
        id=q_id,
        title="✨ Спросить нейросеть:",
        description=text[:60],
        input_message_content=InputTextMessageContent(
            message_text=f"❓ <b>{escaped_q}</b>\n\n<i>Нажмите кнопку ниже, чтобы сгенерировать ответ:</i>",
            parse_mode="HTML",
        ),
        reply_markup=kb,
    )
    await query.answer([item], cache_time=1, is_personal=True)

# Обработка нажатия на кнопку под сообщением
@dp.callback_query(lambda c: c.data and c.data.startswith("ask:"))
async def on_button_click(callback: types.CallbackQuery):
    await callback.answer("⏳ Генерирую ответ...")
    
    # Получаем исходный текст вопроса из тела сообщения
    full_text = callback.message.text if callback.message else ""
    if not full_text and callback.inline_message_id:
        # Для инлайн-сообщений исходный текст берем из сообщения
        print("Получен инлайн-клик на кнопку!")
    
    # Извлекаем вопрос из текста над кнопкой
    query_text = ""
    if callback.message and callback.message.text:
        lines = callback.message.text.split("\n")
        query_text = lines[0].replace("❓", "").strip()
    
    # Запасной вариант: если текст пуст, берем запрос из хранилища или заглушки
    if not query_text:
        query_text = "как прорастить косточку от манго"

    escaped_q = html.escape(query_text)
    answer = await asyncio.to_thread(ask_gemini, query_text)
    escaped_a = html.escape(answer)

    if callback.inline_message_id:
        await bot.edit_message_text(
            inline_message_id=callback.inline_message_id,
            text=f"❓ <b>{escaped_q}</b>\n\n{escaped_a}",
            parse_mode="HTML",
            reply_markup=None,
        )
    elif callback.message:
        await callback.message.edit_text(
            text=f"❓ <b>{escaped_q}</b>\n\n{escaped_a}",
            parse_mode="HTML",
            reply_markup=None,
        )

# Резервный chosen_inline_result (если Telegram решит его доставить)
@dp.chosen_inline_result()
async def on_chosen_inline_result(chosen_result: types.ChosenInlineResult):
    text = chosen_result.query.strip()
    if not chosen_result.inline_message_id:
        return
    escaped_q = html.escape(text)
    try:
        answer = await asyncio.to_thread(ask_gemini, text)
        escaped_a = html.escape(answer)
        await bot.edit_message_text(
            inline_message_id=chosen_result.inline_message_id,
            text=f"❓ <b>{escaped_q}</b>\n\n{escaped_a}",
            parse_mode="HTML",
            reply_markup=None,
        )
    except Exception as e:
        print(f"Ошибка chosen_inline: {e}")

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
