import random

# Вспомогательная функция для перевода и улучшения промпта через Gemini
def translate_prompt_to_en(ru_prompt: str) -> str:
    try:
        res = ai_client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=f"Translate this image generation prompt to detailed English for Stable Diffusion. Output ONLY the English prompt, no other text: {ru_prompt}",
            config={"max_output_tokens": 80, "temperature": 0.2}
        )
        if res.text:
            return res.text.strip().replace("\n", " ")
    except Exception as e:
        print(f"Ошибка перевода промпта: {e}", flush=True)
    return ru_prompt

@dp.inline_query()
async def inline_handler(query: types.InlineQuery):
    text = query.query.strip()
    if len(text) < 2:
        return

    lower = text.lower()

    # Генерация изображений
    if any(lower.startswith(prefix) for prefix in ["нарисуй", "фото", "картинка", "draw"]):
        clean_prompt = text
        for p in ["нарисуй", "фото", "картинка", "draw"]:
            if lower.startswith(p):
                clean_prompt = text[len(p):].strip()
                break

        # 1. Переводим в понятный для диффузии английский промпт
        en_prompt = await asyncio.to_thread(translate_prompt_to_en, clean_prompt)
        
        # 2. Генерируем уникальный seed, чтобы сбить старый кэш
        seed = random.randint(1, 999999)
        encoded = urllib.parse.quote(en_prompt)
        image_url = f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&seed={seed}&nologo=true"

        q_id = hashlib.md5(f"{text}_{seed}".encode("utf-8")).hexdigest()

        item = InlineQueryResultPhoto(
            id=q_id,
            photo_url=image_url,
            thumbnail_url=image_url,
            caption=f"🎨 <b>Запрос:</b> {html.escape(clean_prompt)}",
            parse_mode="HTML",
        )
        # cache_time=0 отключает залипание старых картинок
        await query.answer([item], cache_time=0, is_personal=True)
        return

    # Обычный текстовый запрос к Gemini
    q_id = hashlib.md5(text.encode("utf-8")).hexdigest()
    answer = await asyncio.to_thread(ask_gemini, text)
    escaped_q = html.escape(text)
    escaped_a = html.escape(answer)

    item = InlineQueryResultArticle(
        id=q_id,
        title=f"Ответ: {text[:35]}",
        description=answer[:80],
        input_message_content=InputTextMessageContent(
            message_text=f"❓ <b>{escaped_q}</b>\n\n{escaped_a}",
            parse_mode="HTML",
        ),
    )
    await query.answer([item], cache_time=60, is_personal=True)
