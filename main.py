import asyncio
import hashlib
import html
import io
import json
import logging
import os
import random
import urllib.parse
import urllib.request
import warnings
from datetime import datetime, timezone
from aiogram import Bot, Dispatcher, F, types
from aiogram.types import (
    InlineQueryResultArticle,
    InlineQueryResultPhoto,
    InputTextMessageContent,
)
from google import genai
from google.genai import types as genai_types

# Подавление предупреждений библиотеки google-genai об AFC
logging.getLogger("google.genai").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", message=".*Automatic function calling.*")
warnings.filterwarnings("ignore", message=".*automatic function calling.*")

# Попытка импорта DDGS (для текстового веб-поиска)
try:
    from duckduckgo_search import DDGS
except ImportError:
    try:
        from ddgs import DDGS
    except ImportError:
        DDGS = None

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
ai_client = genai.Client(api_key=GEMINI_API_KEY)

# Актуальные модели Google Gemini
MODELS_POOL = ["gemini-3.6-flash", "gemini-3.5-flash-lite"][cite: 1, 2]
DAILY_LIMIT = 1500[cite: 1, 2]

usage_stats = {
    "current_date": datetime.now(timezone.utc).date(),
    "requests_today": 0,
}[cite: 1, 2]

SYSTEM_INSTRUCTION = (
    "Ты — остроумный, прямой и свойский товарищ с отличным чувством юмора. "
    "Общайся неформально, на равных, живым современным языком. "
    "Мат используй только для эмоций, удачной шутки или связки слов, когда это реально к месту. "
    "К пользователю относись тепло и по-дружески: не груби, не быкуй и не токсичь. "
    "Отвечай емко, без лишней воды и духоты, но действительно полезно и по фактам."
)[cite: 1, 2]

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
][cite: 1, 2]

SEARCH_TRIGGERS = ("найди", "поищи", "поиск", "гугл", "аккорды", "новости")[cite: 1, 2]
LYRICS_TRIGGERS = ("текст песни", "слова песни", "lyrics", "текст ")[cite: 1, 2]
PIC_TRIGGERS = ("pic", "пик", "найди фото", "фото")[cite: 1, 2]

def track_usage():
    today = datetime.now(timezone.utc).date()[cite: 1, 2]
    if usage_stats["current_date"] != today:[cite: 1, 2]
        usage_stats["current_date"] = today[cite: 1, 2]
        usage_stats["requests_today"] = 0[cite: 1, 2]
    usage_stats["requests_today"] += 1[cite: 1, 2]

def quick_translate_to_en(text: str) -> str:
    """Быстрый перевод запроса через Google Translate API для качественного поиска фото."""
    if not any(ord(c) > 127 for c in text):[cite: 1, 2]
        return text[cite: 1, 2]
    try:
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=en&dt=t&q={urllib.parse.quote(text)}"[cite: 1, 2]
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})[cite: 1, 2]
        with urllib.request.urlopen(req, timeout=3) as resp:[cite: 1, 2]
            data = json.loads(resp.read().decode("utf-8"))[cite: 1, 2]
            return "".join([part[0] for part in data[0] if part[0]]).strip()[cite: 1, 2]
    except Exception:
        return text[cite: 1, 2]

def search_web_images(query: str, max_results: int = 8) -> list:
    """Стабильный открытый поиск картинок без API-ключей, 401 и 403 блокировок."""
    items = [][cite: 1, 2]
    en_query = quick_translate_to_en(query)[cite: 1, 2]
    
    # Wikimedia Commons API (не требует авторизации, выдает прямые ссылки на JPG/PNG)
    for q in [query, en_query]:[cite: 1, 2]
        if items:[cite: 1, 2]
            break[cite: 1, 2]
        try:
            encoded = urllib.parse.quote(q)[cite: 1, 2]
            url = (
                f"https://commons.wikimedia.org/w/api.php?action=query"
                f"&generator=search&gsrnamespace=6&gsrsearch={encoded}"
                f"&gsrlimit={max_results * 2}&prop=imageinfo&iiprop=url|size"
                f"&format=json"
            )[cite: 1, 2]
            req = urllib.request.Request(url, headers={"User-Agent": "TelegramBotSearch/3.0 (contact@bot.local)"})[cite: 1, 2]
            with urllib.request.urlopen(req, timeout=5) as resp:[cite: 1, 2]
                data = json.loads(resp.read().decode("utf-8"))[cite: 1, 2]
                pages = data.get("query", {}).get("pages", {})[cite: 1, 2]
                for _, page_info in pages.items():[cite: 1, 2]
                    info_list = page_info.get("imageinfo")[cite: 1, 2]
                    if not info_list:[cite: 1, 2]
                        continue[cite: 1, 2]
                    img_url = info_list[0].get("url", "")[cite: 1, 2]
                    # Telegram принимает только прямые растровые картинки
                    if any(img_url.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png"]):[cite: 1, 2]
                        items.append({
                            "image": img_url,
                            "thumb": img_url,
                            "title": page_info.get("title", "Image").replace("File:", "")
                        })[cite: 1, 2]
                    if len(items) >= max_results:[cite: 1, 2]
                        break[cite: 1, 2]
        except Exception as e:
            print(f"Ошибка поиска Wikimedia ({q}): {e}", flush=True)[cite: 1, 2]

    return items[cite: 1, 2]

def fetch_song_lyrics(query: str) -> str:
    """Точный поиск реального текста песни через базу LRCLIB."""
    clean = query.lower()[cite: 1, 2]
    for word in ["найди", "дай", "текст песни", "слова песни", "lyrics", "песня", "песни", "текст"]:[cite: 1, 2]
        clean = clean.replace(word, " ")[cite: 1, 2]
    clean = clean.strip()[cite: 1, 2]
    if not clean:[cite: 1, 2]
        return ""[cite: 1, 2]

    try:
        url = f"https://lrclib.net/api/search?q={urllib.parse.quote(clean)}"[cite: 1, 2]
        req = urllib.request.Request(url, headers={"User-Agent": "TelegramMusicBot/1.0"})[cite: 1, 2]
        with urllib.request.urlopen(req, timeout=5) as response:[cite: 1, 2]
            data = json.loads(response.read().decode("utf-8"))[cite: 1, 2]
            if data and isinstance(data, list):[cite: 1, 2]
                for track in data:[cite: 1, 2]
                    lyrics = track.get("plainLyrics")[cite: 1, 2]
                    if lyrics:[cite: 1, 2]
                        title = track.get("trackName", "Трек")[cite: 1, 2]
                        artist = track.get("artistName", "Исполнитель")[cite: 1, 2]
                        return f"🎶 <b>{html.escape(artist)} — {html.escape(title)}</b>\n\n{html.escape(lyrics[:3800])}"[cite: 1, 2]
    except Exception as e:
        print(f"Ошибка получения текста: {e}", flush=True)[cite: 1, 2]
    return ""[cite: 1, 2]

def search_web(query: str, max_results: int = 3) -> str:
    """Поиск информации в сети."""
    if DDGS is None:[cite: 1, 2]
        return ""[cite: 1, 2]
    try:
        results = [][cite: 1, 2]
        with DDGS() as ddgs:[cite: 1, 2]
            for r in ddgs.text(query, max_results=max_results):[cite: 1, 2]
                results.append(f"— {r.get('title', '')}: {r.get('body', '')}")[cite: 1, 2]
        if results:[cite: 1, 2]
            return "\n\n".join(results)[cite: 1, 2]
    except Exception as e:
        print(f"Веб-поиск недоступен: {e}", flush=True)[cite: 1, 2]
    return ""[cite: 1, 2]

def ask_gemini(prompt: str) -> str:
    """Генерация ответов через Gemini (сначала 3.6-flash, затем 3.5-flash-lite)."""
    track_usage()[cite: 1, 2]
    lower = prompt.lower()[cite: 1, 2]
    final_prompt = prompt[cite: 1, 2]

    if any(trigger in lower for trigger in SEARCH_TRIGGERS):[cite: 1, 2]
        web_info = search_web(prompt)[cite: 1, 2]
        if web_info:[cite: 1, 2]
            final_prompt = (
                f"Информация из сети:\n{web_info}\n\n"
                f"На основе этих данных ответь на запрос пользователя: {prompt}"
            )[cite: 1, 2]

    for model_name in MODELS_POOL:[cite: 1, 2]
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
            )[cite: 1, 2]
            if response.text:[cite: 1, 2]
                return response.text.strip()[cite: 1, 2]
        except Exception as e:
            print(f"Ошибка модели {model_name}: {e}", flush=True)[cite: 1, 2]
            continue[cite: 1, 2]
    return "Сервер временно перегружен, попробуй еще раз через минуту."[cite: 1, 2]

@dp.message(F.text.in_({"/limit", "/stats", "/лимит"}))
async def check_limits(message: types.Message):
    today = datetime.now(timezone.utc).date()[cite: 1, 2]
    if usage_stats["current_date"] != today:[cite: 1, 2]
        usage_stats["current_date"] = today[cite: 1, 2]
        usage_stats["requests_today"] = 0[cite: 1, 2]

    spent = usage_stats["requests_today"][cite: 1, 2]
    left = max(0, DAILY_LIMIT - spent)[cite: 1, 2]
    
    text = (
        f"📊 <b>Статистика бесплатных запросов</b>\n\n"
        f"• Потрачено сегодня: <b>{spent}</b>\n"
        f"• Осталось: <b>{left}</b> из {DAILY_LIMIT}\n"
        f"• Сброс счетчика: полночь UTC (~10:00-11:00 МСК)"
    )[cite: 1, 2]
    await message.reply(text, parse_mode="HTML")[cite: 1, 2]

@dp.message(F.text.in_({"/start", "/reset"}))
async def cmd_start(message: types.Message):
    await message.reply(
        "👋 Здорово! Я на связи.\n\n"
        "• <b>Поиск фото:</b> @nikitaGODai_bot pic <запрос>\n"
        "• <b>Генерация картинок:</b> @nikitaGODai_bot нарисуй <запрос>\n"
        "• <b>Тексты треков:</b> 'текст песни <название>'\n"
        "• <b>Лимиты:</b> /limit"
    )[cite: 1, 2]

@dp.message(F.text)
async def message_handler(message: types.Message):
    text = message.text.strip()[cite: 1, 2]
    lower = text.lower()[cite: 1, 2]

    if any(trig in lower for trig in LYRICS_TRIGGERS):[cite: 1, 2]
        status_msg = await message.reply("🎶 Ищу слова трека в базе...")[cite: 1, 2]
        lyrics = await asyncio.to_thread(fetch_song_lyrics, text)[cite: 1, 2]
        if lyrics:[cite: 1, 2]
            await status_msg.edit_text(lyrics, parse_mode="HTML")[cite: 1, 2]
        else:
            await status_msg.edit_text(
                "Не нашел этот трек в базе. Попробуй написать так:\n"
                "<code>текст Bladee Topman</code>", 
                parse_mode="HTML"
            )[cite: 1, 2]
        return[cite: 1, 2]

    status_msg = await message.reply("⏳ Соображаю...")[cite: 1, 2]
    answer = await asyncio.to_thread(ask_gemini, text)[cite: 1, 2]
    await status_msg.edit_text(answer)[cite: 1, 2]

@dp.message(F.photo)
async def photo_handler(message: types.Message):
    track_usage()[cite: 1, 2]
    status_msg = await message.reply("🔍 Смотрю, что тут...")[cite: 1, 2]
    photo = message.photo[-1][cite: 1, 2]
    file_io = io.BytesIO()[cite: 1, 2]
    await bot.download(photo, destination=file_io)[cite: 1, 2]
    image_bytes = file_io.getvalue()[cite: 1, 2]

    caption = message.caption.strip() if message.caption else "Что на этой картинке?"[cite: 1, 2]

    try:
        response = await asyncio.to_thread(
            ai_client.models.generate_content,
            model="gemini-3.6-flash",
            contents=[
                {"inline_data": {"mime_type": "image/jpeg", "data": image_bytes}},
                caption,
            ],
            config={
                "system_instruction": SYSTEM_INSTRUCTION,
                "safety_settings": SAFETY_SETTINGS,
                "temperature": 0.72,
            }
        )[cite: 1, 2]
        await status_msg.edit_text(response.text if response.text else "Не удалось разобрать картинку.")[cite: 1, 2]
    except Exception as e:
        print(f"Ошибка фото: {e}", flush=True)[cite: 1, 2]
        await status_msg.edit_text("Что-то пошло не так при обработке фото.")[cite: 1, 2]

# ----------------- ИНЛАЙН РЕЖИМ -----------------
@dp.inline_query()
async def inline_handler(query: types.InlineQuery):
    text = query.query.strip()[cite: 1, 2]
    if len(text) < 2:[cite: 1, 2]
        return[cite: 1, 2]

    lower = text.lower()[cite: 1, 2]

    # 1. ПОИСК ФОТО (АНАЛОГ @pic)
    if any(lower.startswith(p) for p in PIC_TRIGGERS):[cite: 1, 2]
        clean_query = text[cite: 1, 2]
        for p in PIC_TRIGGERS:[cite: 1, 2]
            if lower.startswith(p):[cite: 1, 2]
                clean_query = text[len(p):].strip()[cite: 1, 2]
                break[cite: 1, 2]

        if clean_query:[cite: 1, 2]
            images = await asyncio.to_thread(search_web_images, clean_query)[cite: 1, 2]
            if images:[cite: 1, 2]
                items = [][cite: 1, 2]
                for idx, img in enumerate(images):[cite: 1, 2]
                    q_id = hashlib.md5(f"pic_{clean_query}_{idx}".encode("utf-8")).hexdigest()[cite: 1, 2]
                    items.append(
                        InlineQueryResultPhoto(
                            id=q_id,
                            photo_url=img["image"],
                            thumbnail_url=img["thumb"],
                            caption=f"🔍 <b>Фото:</b> {html.escape(clean_query)}",
                            parse_mode="HTML",
                        )
                    )[cite: 1, 2]
                await query.answer(items, cache_time=120, is_personal=True)[cite: 1, 2]
                return[cite: 1, 2]
            else:
                q_id = hashlib.md5(f"err_{clean_query}".encode("utf-8")).hexdigest()[cite: 1, 2]
                item = InlineQueryResultArticle(
                    id=q_id,
                    title="Картинки не найдены",
                    description="Попробуй изменить запрос",
                    input_message_content=InputTextMessageContent(
                        message_text=f"По запросу '{clean_query}' картинок не нашлось.",
                    ),
                )[cite: 1, 2]
                await query.answer([item], cache_time=1, is_personal=True)[cite: 1, 2]
                return[cite: 1, 2]

    # 2. ГЕНЕРАЦИЯ АРТОВ
    if any(lower.startswith(p) for p in ["нарисуй", "draw", "картинка"]):[cite: 1, 2]
        clean_prompt = text[cite: 1, 2]
        for p in ["нарисуй", "draw", "картинка"]:[cite: 1, 2]
            if lower.startswith(p):[cite: 1, 2]
                clean_prompt = text[len(p):].strip()[cite: 1, 2]
                break[cite: 1, 2]

        en_prompt = quick_translate_to_en(clean_prompt)[cite: 1, 2]
        seed = random.randint(1, 999999)[cite: 1, 2]
        encoded = urllib.parse.quote(en_prompt)[cite: 1, 2]
        image_url = f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&seed={seed}&nologo=true"[cite: 1, 2]

        q_id = hashlib.md5(f"art_{text}_{seed}".encode("utf-8")).hexdigest()[cite: 1, 2]
        item = InlineQueryResultPhoto(
            id=q_id,
            photo_url=image_url,
            thumbnail_url=image_url,
            caption=f"🎨 <b>Запрос:</b> {html.escape(clean_prompt)}",
            parse_mode="HTML",
        )[cite: 1, 2]
        await query.answer([item], cache_time=0, is_personal=True)[cite: 1, 2]
        return[cite: 1, 2]

    # 3. ТЕКСТЫ ПЕСЕН
    if any(trig in lower for trig in LYRICS_TRIGGERS):[cite: 1, 2]
        lyrics = await asyncio.to_thread(fetch_song_lyrics, text)[cite: 1, 2]
        if lyrics:[cite: 1, 2]
            q_id = hashlib.md5(text.encode("utf-8")).hexdigest()[cite: 1, 2]
            item = InlineQueryResultArticle(
                id=q_id,
                title="Слова трека",
                description=text[:40],
                input_message_content=InputTextMessageContent(
                    message_text=lyrics,
                    parse_mode="HTML",
                ),
            )[cite: 1, 2]
            await query.answer([item], cache_time=60, is_personal=True)[cite: 1, 2]
            return[cite: 1, 2]

    # 4. ТЕКСТОВЫЕ ОТВЕТЫ GEMINI
    q_id = hashlib.md5(text.encode("utf-8")).hexdigest()[cite: 1, 2]
    answer = await asyncio.to_thread(ask_gemini, text)[cite: 1, 2]
    escaped_q = html.escape(text)[cite: 1, 2]
    escaped_a = html.escape(answer)[cite: 1, 2]

    item = InlineQueryResultArticle(
        id=q_id,
        title=f"Ответ: {text[:35]}",
        description=answer[:80],
        input_message_content=InputTextMessageContent(
            message_text=f"🐏 <b>{escaped_q}</b>\n\n{escaped_a}",
            parse_mode="HTML",
        ),
    )[cite: 1, 2]
    await query.answer([item], cache_time=60, is_personal=True)[cite: 1, 2]

async def main():
    await bot.delete_webhook(drop_pending_updates=True)[cite: 1, 2]
    await asyncio.sleep(1)[cite: 1, 2]
    print("Бот запущен на актуальных моделях Gemini 3.6 / 3.5!", flush=True)[cite: 1, 2]
    await dp.start_polling(bot, allowed_updates=["message", "inline_query"])[cite: 1, 2]

if __name__ == "__main__":
    asyncio.run(main())[cite: 1, 2]
