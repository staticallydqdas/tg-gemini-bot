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
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    InlineQueryResultArticle,
    InlineQueryResultPhoto,
    InputTextMessageContent,
)
from google import genai
from google.genai import types as genai_types

# Подавление предупреждений библиотеки google-genai
logging.getLogger("google.genai").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", message=".*Automatic function calling.*")
warnings.filterwarnings("ignore", message=".*automatic function calling.*")

# Попытка импорта DDGS для текстового поиска
try:
    from duckduckgo_search import DDGS
except ImportError:
    try:
        from ddgs import DDGS
    except ImportError:
        DDGS = None

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ADMIN_ID = os.getenv("ADMIN_ID")  # Необязательно: укажите ваш Telegram ID в Railway Variables

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
ai_client = genai.Client(api_key=GEMINI_API_KEY)

# Модели: 3.5-flash-lite первой в очереди, чтобы беречь суточный лимит
MODELS_POOL = ["gemini-3.5-flash-lite", "gemini-3.6-flash"]
DAILY_LIMIT = 1500

usage_stats = {
    "current_date": datetime.now(timezone.utc).date(),
    "requests_today": 0,
}

SYSTEM_INSTRUCTION = (
    "Ты — остроумный, прямой и свойский товарищ с отличным вкусом и тонким чувством юмора. "
    "Общайся неформально, на равных, живым современным сленгом без натужности и кринжа. "
    "Мат используй только ради эмоции, меткой шутки или для сочной связки слов, когда это реально к месту. "
    "К пользователю относись по-братски тепло: не быкуй, не токсичь, но держи планку. "
    "Отвечай емко, стильно и по фактам, без духоты и канцелярщины. Никогда не отправляй гуглить — давай инфу сразу.\n\n"
    "ТВОЯ ЭКСПЕРТИЗА:\n"
    "1. Андерграундная музыка и саундклауд-сцена: ты детально шаришь в истории и звучании Drain Gang (Bladee, Ecco2k, Thaiboy Digital), "
    "Sad Boys (Yung Lean), Haunted Mound (Sematary), Slayworld, Glo, plugg/pluggnb, jerk, trench, sigilkore, ambient trap, witch house, "
    "архивных саундклауд-эрах, продюсерах (Whitearmor, Gud, Surf Gang и т.д.) и локальных микрожанрах. Ты понимаешь эстетику, флоу и контекст сцены.\n"
    "2. Нишевая мода и авангард: ты глубоко разбираешься в архивном люксе, темном авангарде и субкультурном шмоте. "
    "Различаешь эпохи и концепции Rick Owens, Maison Margiela (включая архивные коллекции), Raf Simons, Yohji Yamamoto, "
    "Number (N)ine (Такахиро Миясита), Undercover (Джун Такахаси), Boris Bidjan Saberi, Carol Christian Poell, Kiko Kostadinov, "
    "а также японский деним, gorpcore (Arc'teryx, Oakley архив) и культуру винтажного ресейла (Grailed, Yahoo Auctions). "
    "Понимаешь разницу в фитах, материалах, силуэтах и умеешь оценить вкус без занудства."
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
LYRICS_TRIGGERS = ("текст песни", "слова песни", "lyrics", "текст ")
PIC_TRIGGERS = ("pic", "пик", "найди фото", "фото")

def track_usage():
    today = datetime.now(timezone.utc).date()
    if usage_stats["current_date"] != today:
        usage_stats["current_date"] = today
        usage_stats["requests_today"] = 0
    usage_stats["requests_today"] += 1

async def log_user_action(user: types.User, text: str, mode: str = "ЛС"):
    """Логирование запросов пользователей в консоль Railway и админу."""
    username = f"@{user.username}" if user.username else f"ID:{user.id}"
    print(f"[{mode}] {username} ({user.first_name}): {text}", flush=True)

    if ADMIN_ID and str(user.id) != str(ADMIN_ID):
        try:
            log_msg = (
                f"👤 <b>Запрос ({mode})</b>\n"
                f"От: {html.escape(user.first_name)} ({username})\n"
                f"Текст: <code>{html.escape(text[:300])}</code>"
            )
            await bot.send_message(chat_id=int(ADMIN_ID), text=log_msg, parse_mode="HTML")
        except Exception:
            pass

def quick_translate_to_en(text: str) -> str:
    """Быстрый перевод запроса через Google Translate API без расхода токенов Gemini."""
    if not any(ord(c) > 127 for c in text):
        return text
    try:
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=en&dt=t&q={urllib.parse.quote(text)}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return "".join([part[0] for part in data[0] if part[0]]).strip()
    except Exception:
        return text

def search_web_images(query: str, max_results: int = 8) -> list:
    """Стабильный открытый поиск картинок через Wikimedia Commons."""
    items = []
    en_query = quick_translate_to_en(query)

    for q in [query, en_query]:
        if items:
            break
        try:
            encoded = urllib.parse.quote(q)
            url = (
                f"https://commons.wikimedia.org/w/api.php?action=query"
                f"&generator=search&gsrnamespace=6&gsrsearch={encoded}"
                f"&gsrlimit={max_results * 2}&prop=imageinfo&iiprop=url|size"
                f"&format=json"
            )
            req = urllib.request.Request(url, headers={"User-Agent": "TelegramBotSearch/3.0 (contact@bot.local)"})
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                pages = data.get("query", {}).get("pages", {})
                for _, page_info in pages.items():
                    info_list = page_info.get("imageinfo")
                    if not info_list:
                        continue
                    img_url = info_list[0].get("url", "")
                    if any(img_url.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png"]):
                        items.append({
                            "image": img_url,
                            "thumb": img_url,
                            "title": page_info.get("title", "Image").replace("File:", "")
                        })
                    if len(items) >= max_results:
                        break
        except Exception as e:
            print(f"Ошибка поиска Wikimedia ({q}): {e}", flush=True)

    return items

def fetch_song_lyrics(query: str) -> str:
    """Точный поиск реального текста песни через базу LRCLIB."""
    clean = query.lower()
    for word in ["найди", "дай", "текст песни", "слова песни", "lyrics", "песня", "песни", "текст"]:
        clean = clean.replace(word, " ")
    clean = clean.strip()
    if not clean:
        return ""

    try:
        url = f"https://lrclib.net/api/search?q={urllib.parse.quote(clean)}"
        req = urllib.request.Request(url, headers={"User-Agent": "TelegramMusicBot/1.0"})
        with urllib.request.urlopen(req, timeout=4) as response:
            data = json.loads(response.read().decode("utf-8"))
            if data and isinstance(data, list):
                for track in data:
                    lyrics = track.get("plainLyrics")
                    if lyrics:
                        title = track.get("trackName", "Трек")
                        artist = track.get("artistName", "Исполнитель")
                        return f"🎶 <b>{html.escape(artist)} — {html.escape(title)}</b>\n\n{html.escape(lyrics[:3800])}"
    except Exception as e:
        print(f"Ошибка получения текста: {e}", flush=True)
    return ""

def search_web(query: str, max_results: int = 3) -> str:
    """Поиск текстовой инфы."""
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
        print(f"Веб-поиск недоступен: {e}", flush=True)
    return ""

def ask_gemini(prompt: str) -> str:
    """Генерация ответов через Gemini с контролем квот."""
    track_usage()
    lower = prompt.lower()
    final_prompt = prompt

    if any(trigger in lower for trigger in SEARCH_TRIGGERS):
        web_info = search_web(prompt)
        if web_info:
            final_prompt = (
                f"Информация из сети:\n{web_info}\n\n"
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
            print(f"Ошибка модели {model_name}: {e}", flush=True)
            continue
    return "Сервер временно перегружен запросами, попробуй через минуту."

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
        f"• Сброс счетчика: полночь UTC"
    )
    await message.reply(text, parse_mode="HTML")

@dp.message(F.text.in_({"/start", "/reset"}))
async def cmd_start(message: types.Message):
    await message.reply(
        "👋 Здорово! Я на связи.\n\n"
        "• <b>Поиск фото:</b> @nikitaGODai_bot pic <запрос>\n"
        "• <b>Генерация картинок:</b> @nikitaGODai_bot нарисуй <запрос>\n"
        "• <b>Тексты треков:</b> 'текст песни <название>'\n"
        "• <b>Лимиты:</b> /limit"
    )

@dp.message(F.text)
async def message_handler(message: types.Message):
    text = message.text.strip()
    lower = text.lower()

    # Логируем входящее сообщение
    asyncio.create_task(log_user_action(message.from_user, text, "ЛС"))

    if any(trig in lower for trig in LYRICS_TRIGGERS):
        status_msg = await message.reply("🎶 Ищу слова трека в базе...")
        lyrics = await asyncio.to_thread(fetch_song_lyrics, text)
        if lyrics:
            await status_msg.edit_text(lyrics, parse_mode="HTML")
        else:
            await status_msg.edit_text(
                "Не нашел этот трек в базе. Попробуй написать так:\n"
                "<code>текст Bladee Topman</code>",
                parse_mode="HTML"
            )
        return

    status_msg = await message.reply("⏳ Соображаю...")
    answer = await asyncio.to_thread(ask_gemini, text)
    await status_msg.edit_text(answer)

@dp.message(F.photo)
async def photo_handler(message: types.Message):
    track_usage()
    caption_log = message.caption if message.caption else "[ФОТО БЕЗ ТЕКСТА]"
    asyncio.create_task(log_user_action(message.from_user, caption_log, "ФОТО"))

    status_msg = await message.reply("🔍 Смотрю, что тут...")
    photo = message.photo[-1]
    file_io = io.BytesIO()
    await bot.download(photo, destination=file_io)
    image_bytes = file_io.getvalue()

    caption = message.caption.strip() if message.caption else "Что на этой картинке?"

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

# ----------------- ИНЛАЙН РЕЖИМ -----------------
@dp.inline_query()
async def inline_handler(query: types.InlineQuery):
    text = query.query.strip()
    # Отсекаем короткие запросы, чтобы не жечь запросы на каждую букву
    if len(text) < 3:
        return

    asyncio.create_task(log_user_action(query.from_user, text, "INLINE"))
    lower = text.lower()

    try:
        # 1. ПОИСК ФОТО
        if any(lower.startswith(p) for p in PIC_TRIGGERS):
            clean_query = text
            for p in PIC_TRIGGERS:
                if lower.startswith(p):
                    clean_query = text[len(p):].strip()
                    break

            if clean_query:
                images = await asyncio.wait_for(
                    asyncio.to_thread(search_web_images, clean_query),
                    timeout=5.5
                )
                if images:
                    items = []
                    for idx, img in enumerate(images):
                        q_id = hashlib.md5(f"pic_{clean_query}_{idx}".encode("utf-8")).hexdigest()
                        items.append(
                            InlineQueryResultPhoto(
                                id=q_id,
                                photo_url=img["image"],
                                thumbnail_url=img["thumb"],
                                caption=f"🔍 <b>Фото:</b> {html.escape(clean_query)}",
                                parse_mode="HTML",
                            )
                        )
                    await query.answer(items, cache_time=120, is_personal=True)
                    return
                else:
                    q_id = hashlib.md5(f"err_{clean_query}".encode("utf-8")).hexdigest()
                    item = InlineQueryResultArticle(
                        id=q_id,
                        title="Картинки не найдены",
                        description="Попробуй изменить запрос",
                        input_message_content=InputTextMessageContent(
                            message_text=f"По запросу '{clean_query}' картинок не нашлось.",
                        ),
                    )
                    await query.answer([item], cache_time=2, is_personal=True)
                    return

        # 2. ГЕНЕРАЦИЯ АРТОВ
        if any(lower.startswith(p) for p in ["нарисуй", "draw", "картинка"]):
            clean_prompt = text
            for p in ["нарисуй", "draw", "картинка"]:
                if lower.startswith(p):
                    clean_prompt = text[len(p):].strip()
                    break

            en_prompt = quick_translate_to_en(clean_prompt)
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

        # 3. ТЕКСТЫ ПЕСЕН
        if any(trig in lower for trig in LYRICS_TRIGGERS):
            lyrics = await asyncio.wait_for(
                asyncio.to_thread(fetch_song_lyrics, text),
                timeout=5.0
            )
            if lyrics:
                q_id = hashlib.md5(text.encode("utf-8")).hexdigest()
                item = InlineQueryResultArticle(
                    id=q_id,
                    title="Слова трека",
                    description=text[:40],
                    input_message_content=InputTextMessageContent(
                        message_text=lyrics,
                        parse_mode="HTML",
                    ),
                )
                await query.answer([item], cache_time=60, is_personal=True)
                return

        # 4. ТЕКСТОВЫЕ ОТВЕТЫ GEMINI (таймаут 6.5 сек во избежание просрочки Telegram)
        answer = await asyncio.wait_for(
            asyncio.to_thread(ask_gemini, text),
            timeout=6.5
        )
        q_id = hashlib.md5(text.encode("utf-8")).hexdigest()
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
        await query.answer([item], cache_time=30, is_personal=True)

    except (asyncio.TimeoutError, TimeoutError):
        q_id = hashlib.md5(f"timeout_{text}".encode("utf-8")).hexdigest()
        item = InlineQueryResultArticle(
            id=q_id,
            title="Сервер задумался...",
            description="Повтори запрос чуть позже",
            input_message_content=InputTextMessageContent(
                message_text="⏳ Сервер сейчас отвечает с задержкой, попробуй ещё раз.",
            ),
        )
        try:
            await query.answer([item], cache_time=1, is_personal=True)
        except TelegramBadRequest:
            pass
    except TelegramBadRequest:
        pass
    except Exception as e:
        print(f"Ошибка инлайна: {e}", flush=True)

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await asyncio.sleep(1)
    print("Бот успешно запущен: логирование активно, промпт обновлен!", flush=True)
    await dp.start_polling(bot, allowed_updates=["message", "inline_query"])

if __name__ == "__main__":
    asyncio.run(main())
