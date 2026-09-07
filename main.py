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

    # Важно: кнопка-заглушка с callback_data, которая заставляет Telegram привязать inline_message_id
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏳ Генерируется ответ...", callback_data="wait")]
        ]
    )

    item = InlineQueryResultArticle(
        id=q_id,
        title="✨ Спросить нейросеть:",
        description=text[:60],
        input_message_content=InputTextMessageContent(
            message_text=f"❓ <b>{escaped_q}</b>\n\n<i>⏳ Нейросеть генерирует ответ...</i>",
            parse_mode="HTML",
        ),
        reply_markup=kb,
    )
    await query.answer([item], cache_time=1, is_personal=True)

# Игнорируем нажатия на кнопку-заглушку, пока думает
@dp.callback_query()
async def callback_handler(callback: types.CallbackQuery):
    await callback.answer()

# Клик по карточке и обновление текста
@dp.chosen_inline_result()
async def on_chosen_inline_result(chosen_result: types.ChosenInlineResult):
    text = chosen_result.query.strip()
    print(f"-> Клик получен: {text}")

    if not chosen_result.inline_message_id:
        print("Ошибка: inline_message_id отсутствует")
        return

    escaped_q = html.escape(text)
    try:
        answer = await asyncio.to_thread(ask_gemini, text)
        escaped_a = html.escape(answer)
        # Обновляем текст и убираем кнопку ожидания (reply_markup=None)
        await bot.edit_message_text(
            inline_message_id=chosen_result.inline_message_id,
            text=f"❓ <b>{escaped_q}</b>\n\n{escaped_a}",
            parse_mode="HTML",
            reply_markup=None,
        )
        print("<- Сообщение в инлайне успешно обновлено")
    except Exception as e:
        print(f"Ошибка edit_message_text: {e}")
        traceback.print_exc()

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
