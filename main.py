import asyncio
import hashlib
import html
import io
import logging
import os
import random
import urllib.parse
from datetime import datetime, timezone
from aiogram import Bot, Dispatcher, F, types
from aiogram.types import (
    InlineQueryResultArticle,
    InlineQueryResultPhoto,
    InputTextMessageContent,
)
from google import genai
from google.genai import types as genai_types

# 1. Поиск DuckDuckGo
try:
    from duckduckgo_search import DDGS
except ImportError:
    DDGS = None

# 2. Подключение к официальному Genius по токену
GENIUS_TOKEN = os.getenv("GENIUS_ACCESS_TOKEN")
genius_client = None
if GENIUS_TOKEN:
    try:
        import lyricsgenius
        genius_client = lyricsgenius.Genius(
            GENIUS_TOKEN,
            verbose=False,
            remove_section_headers=False,
            skip_non_songs=True,
        )
    except Exception as e:
        print(f"Ошибка подключения Genius: {e}", flush=True)

logging.getLogger("google.genai").setLevel(logging.ERROR)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
ai_client = genai.Client(api_key=GEMINI_API_KEY)

MODELS_POOL = ["gemini-3.5-flash-lite", "gemini-2.5-flash"]
DAILY_LIMIT = 1500

usage_stats = {
    "current_date": datetime.now(timezone.utc).date(),
    "requests_today": 0,
}

SYSTEM_INSTRUCTION = (
    "Ты — остроумный, прямой и свойский товарищ с отличным чувством юмора. "
    "Общайся неформально, на равных, живым современным языком. "
    "Мат используй только для эмоций, удачной шутки или связки слов, когда это реально к месту. "
    "К пользователю относись тепло и по-дружески: не груби, не быкуй и не токсичь. "
    "Отвечай емко, без лишней воды и духоты, но действительно полезно и по фактам. "
    "Никогда не отправляй пользователя искать что-то в Google или на сторонние сайты — давай ответы сразу."
)

SAFETY_SETTINGS = [
    genai_types.SafetySetting(
        category=genai_types.HarmCategory.HARM_CATEGORY_HARASSMENT,
        threshold=genai_types.HarmBlockThreshold.BLOCK_NONE,
    ),
    genai_types.SafetySetting(
        category=genai_types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        threshold=genai_types.HarmBlockThreshold.BLOCK_NONE,
    ),
    genai_types.SafetySetting(
        category=genai_types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        threshold=genai_types.HarmBlockThreshold.BLOCK_NONE,
    ),
    genai_types.SafetySetting(
        category=genai_types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        threshold=genai_types.HarmBlockThreshold.BLOCK_NONE,
    ),
]

SEARCH_TRIGGERS = ("найди", "поищи", "поиск", "гугл", "аккорды", "новости")
LYRICS_TRIGGERS = ("текст песни", "слова песни", "lyrics")

def track_usage():
    """Счетчик запросов с автосбросом в полночь UTC."""
    today = datetime.now(timezone.utc).date()
    if usage_stats["current_date"] != today:
        usage_stats["current_date"] = today
        usage_stats["requests_today"] = 0
    usage_stats["requests_today"] += 1

def fetch_song_lyrics(query: str) -> str:
    """Прямой поиск текста песни в базе Genius."""
    if not genius_client:
        return ""
    clean = query.lower()
    for word in ["найди", "текст песни", "слова песни", "lyrics", "песня", "песни"]:
        clean = clean.replace(word, "").strip()
    try:
        song = genius_client.search_song(clean)
        if song and song.lyrics:
            lines = song.lyrics.split("\n")
            lyrics = "\n".join(lines[1:]) if len(lines) > 1 else song.lyrics
            # Ограничение Telegram на длину одного сообщения
            return f"🎶 <b>{html.escape(song.title)} — {html.escape(song.artist)}</b>\n\n{html.escape(lyrics[:3800])}"
    except Exception as e:
        print(f"Ошибка запроса к Genius: {e}", flush=True)
    return ""

def search_web(query: str, max_results: int = 3) -> str:
    """Поиск инфы через DuckDuckGo."""
    if DDGS is None:
        return ""
    try:
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append(f"— {r.get('title', '')}: {r.get('body', '')}")
        if results:
            return "\n\n".join(results)
    except Exception as e:
        print(f"Ошибка поиска DuckDuckGo: {e}", flush=True)
    return ""

def ask_gemini(prompt: str) -> str:
    """Диалог с Gemini с подтягиванием веб-поиска."""
    track_usage()
    lower = prompt.lower()
    final_prompt = prompt

    if any(trigger in lower for trigger in SEARCH_TRIGGERS):
        web_info = search_web(prompt)
        if web_info:
            final_prompt = (
                f"Информация из поисковой выдачи интернета:\n{web_info}\n\n"
                f"На основе этих данных ответь на запрос пользователя: {prompt}"
            )

    for model_name in MODELS_POOL:
        try:
            response = ai_client.models.generate_content(
                model=model_name,
                contents=final_prompt,
                config={
                    "system_instruction": SYSTEM_INSTRUCTION,
                    "max_output_tokens": 700,
                    "temperature": 0.72,
                    "safety_settings": SAFETY_SETTINGS,
                },
            )
            if response.text:
                return response.text.strip()
        except Exception as e:
            print(f"Ошибка {model_name}: {e}", flush=True)
            continue
    return "Сервер временно прилёг отдохнуть, попробуй через минуту."

def translate_prompt_to_en(ru_prompt: str) -> str:
    """Перевод промпта для генератора картинок."""
    track_usage()
    try:
        res = ai_client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=f"Translate this image prompt into a detailed English prompt for text-to-image AI: {ru_prompt}. Return ONLY English text.",
            config={"max_output_tokens": 70, "temperature": 0.2}
        )
        if res.text:
            return res.text.strip().replace("\n", " ")
    except Exception as e:
        print(f"Ошибка перевода: {e}", flush=True)
    return ru_prompt

@dp.message(F.text.in_({"/limit", "/stats", "/лимит"}))
async def check_limits(message: types.Message):
    today = datetime.now(timezone.utc).date()
    if usage_stats["current_date"] != today:
        usage_stats["current_date"] = today
        usage_stats["requests_today"] = 0

    spent = usage_stats["requests_today"]
    left = max(0, DAILY_LIMIT - spent)
    
    text = (
        f"📊 <b>Статистика бесплатных запросов</b>\n\n"
        f"• Потрачено сегодня: <b>{spent}</b>\n"
        f"• Осталось: <b>{left}</b> из {DAILY_LIMIT}\n"
        f"• Сброс счетчика: полночь UTC (~10:00-11:00 МСК)"
    )
    await message.reply(text, parse_mode="HTML")

@dp.message(F.text.in_({"/start", "/reset"}))
async def cmd_start(message: types.Message):
    await message.reply(
        "👋 Здорово! Я на связи.\n\n"
        "• <b>Тексты треков:</b> 'текст песни <название>'\n"
        "• <b>Поиск инфы:</b> напиши 'найди ...'\n"
        "• <b>Генерация картинок в инлайне:</b> @nikitaGODai_bot нарисуй ...\n"
        "• <b>Лимиты:</b> /limit"
    )

@dp.message(F.text)
async def message_handler(message: types.Message):
    text = message.text.strip()
    lower = text.lower()

    # Поиск текста песни через Genius
    if any(trig in lower for trig in LYRICS_TRIGGERS):
        status_msg = await message.reply("🎶 Ищу слова песни на Genius...")
        lyrics = await asyncio.to_thread(fetch_song_lyrics, text)
        if lyrics:
            await status_msg.edit_text(lyrics, parse_mode="HTML")
            return
        # Если не нашел — НЕ отдаем в Gemini, чтобы она не сочиняла бред!
        await status_msg.edit_text("Не удалось найти этот трек на Genius. Попробуй написать название и исполнителя точнее.")
        return

    # Обычные текстовые запросы в Gemini
    status_msg = await message.reply("⏳ Соображаю...")
    answer = await asyncio.to_thread(ask_gemini, text)
    await status_msg.edit_text(answer)

@dp.message(F.photo)
async def photo_handler(message: types.Message):
    track_usage()
    status_msg = await message.reply("🔍 Смотрю, что тут...")
    photo = message.photo[-1]
    file_io = io.BytesIO()
    await bot.download(photo, destination=file_io)
    image_bytes = file_io.getvalue()

    caption = message.caption.strip() if message.caption else "Что тут вообще происходит на изображении?"

    try:
        response = await asyncio.to_thread(
            ai_client.models.generate_content,
            model="gemini-3.5-flash-lite",
            contents=[
                {"inline_data": {"mime_type": "image/jpeg", "data": image_bytes}},
                caption,
            ],
            config={
                "system_instruction": SYSTEM_INSTRUCTION,
                "safety_settings": SAFETY_SETTINGS,
                "temperature": 0.72,
            }
        )
        await status_msg.edit_text(response.text if response.text else "Не удалось разобрать картинку.")
    except Exception as e:
        print(f"Ошибка фото: {e}", flush=True)
        await status_msg.edit_text("Что-то пошло не так при обработке фото.")

@dp.inline_query()
async def inline_handler(query: types.InlineQuery):
    text = query.query.strip()
    if len(text) < 2:
        return

    lower = text.lower()

    # Генерация картинок
    if any(lower.startswith(p) for p in ["нарисуй", "фото", "картинка", "draw"]):
        clean_prompt = text
        for p in ["нарисуй", "фото", "картинка", "draw"]:
            if lower.startswith(p):
                clean_prompt = text[len(p):].strip()
                break

        en_prompt = await asyncio.to_thread(translate_prompt_to_en, clean_prompt)
        seed = random.randint(1, 999999)
        encoded = urllib.parse.quote(en_prompt)
        image_url = f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&seed={seed}&nologo=true"

        q_id = hashlib.md5(f"art_{text}_{seed}".encode("utf-8")).hexdigest()
        item = InlineQueryResultPhoto(
            id=q_id,
            photo_url=image_url,
            thumbnail_url=image_url,
            caption=f"🎨 <b>Запрос:</b> {html.escape(clean_prompt)}",
            parse_mode="HTML",
        )
        await query.answer([item], cache_time=0, is_personal=True)
        return

    # Поиск текстов в инлайне
    if any(trig in lower for trig in LYRICS_TRIGGERS):
        lyrics = await asyncio.to_thread(fetch_song_lyrics, text)
        if lyrics:
            q_id = hashlib.md5(text.encode("utf-8")).hexdigest()
            item = InlineQueryResultArticle(
                id=q_id,
                title="Слова трека (Genius)",
                description=text[:40],
                input_message_content=InputTextMessageContent(
                    message_text=lyrics,
                    parse_mode="HTML",
                ),
            )
            await query.answer([item], cache_time=60, is_personal=True)
            return

    # Обычные текстовые ответы Gemini в инлайне
    q_id = hashlib.md5(text.encode("utf-8")).hexdigest()
    answer = await asyncio.to_thread(ask_gemini, text)
    escaped_q = html.escape(text)
    escaped_a = html.escape(answer)

    item = InlineQueryResultArticle(
        id=q_id,
        title=f"Ответ: {text[:35]}",
        description=answer[:80],
        input_message_content=InputTextMessageContent(
            message_text=f"🐏 <b>{escaped_q}</b>\n\n{escaped_a}",
            parse_mode="HTML",
        ),
    )
    await query.answer([item], cache_time=60, is_personal=True)

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await asyncio.sleep(1)
    print("Бот запущен с официальным токеном Genius!", flush=True)
    await dp.start_polling(bot, allowed_updates=["message", "inline_query"])

if __name__ == "__main__":
    asyncio.run(main())
