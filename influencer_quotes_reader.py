# influencer_quotes_reader.py
# v3.0 – 10-Jun-2025
#
# GPT теперь выступает в роли умного редактора:
# 1. Фильтрует бессмысленные цитаты.
# 2. Определяет тематику каждой цитаты по ее содержанию.
# 3. Делает качественный перевод.

import os
import time
import html
import re
import requests
import openai
import json
from datetime import datetime, timedelta
from custom_logger import log

# --- Конфигурация GPT ---
GPT_MODEL_FOR_PROCESSING = "gpt-4o-mini"

def _process_quotes_with_gpt(raw_quotes: list[str]) -> list:
    """
    Отправляет "сырые" цитаты в GPT для фильтрации, категоризации и перевода.
    Возвращает список словарей для осмысленных цитат.
    """
    if not raw_quotes:
        return []

    # Создаем нумерованный список для промпта
    numbered_quotes_str = "\n".join([f'{i+1}. "{quote}"' for i, quote in enumerate(raw_quotes)])

    prompt = f"""
Ты — строгий и умный редактор финансового Telegram-канала. Тебе дан список "сырых" фрагментов текста.
Твоя задача — в три этапа обработать каждый фрагмент:

Этап 1: ОЦЕНКА. Проанализируй каждый фрагмент. Является ли он осмысленным, самодостаточным высказыванием или мнением?
Отбрасывай (игнорируй) фрагменты, если они являются:
- Просто набором хэштегов.
- Заголовком статьи или видео, а не цитатой из него.
- Новостью О человеке, а не ЕГО мнением (например, "аналитики обсуждают слова Трампа" — это мусор).
- Бессмысленным обрывком фразы без контекста.
- Просто ссылкой (URL).

Этап 2: КАТЕГОРИЗАЦИЯ. Для каждого фрагмента, прошедшего оценку, определи его главную тему по содержанию. Тема может быть только 'crypto' или 'stock'.
- 'crypto': если речь о криптовалютах, блокчейне, NFT, токенах (BTC, ETH и т.д.).
- 'stock': если речь о фондовом рынке, акциях, экономике, традиционных компаниях.

Этап 3: ПЕРЕВОД. Выполни качественный, "органический" перевод на русский язык для каждого осмысленного фрагмента. Перевод должен быть естественным, как будто его написал носитель языка.

Формат ответа:
Верни результат в виде JSON-массива. Каждый элемент массива — это объект для ОДНОЙ осмысленной цитаты.
Каждый объект должен содержать три ключа:
- "original_index": номер оригинального фрагмента из списка (начиная с 1).
- "theme": определенная тобой тема ('crypto' или 'stock').
- "translated_quote": твой качественный перевод.

Если ни один из фрагментов не прошел твою оценку, верни пустой массив [].

"Сырые" фрагменты для обработки:
---
{numbered_quotes_str}
---

Твой JSON-ответ:
"""
    try:
        if not openai.api_key:
            log("CRITICAL: OpenAI API key not set. Cannot process quotes.")
            return []

        log(f"INFO: Отправка {len(raw_quotes)} фрагментов в GPT для фильтрации и анализа...")
        response = openai.ChatCompletion.create(
            model=GPT_MODEL_FOR_PROCESSING,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=3000,
            response_format={"type": "json_object"}
        )
        response_text = response.choices[0].message.content.strip()
        
        # GPT-4o с `json_object` может вернуть JSON как строку внутри корневого объекта
        # Например: {"quotes": [...]}. Пытаемся извлечь массив.
        parsed_json = json.loads(response_text)
        processed_quotes = next(iter(parsed_json.values())) # Берем значение первого ключа

        if isinstance(processed_quotes, list):
            log(f"INFO: GPT обработал и вернул {len(processed_quotes)} осмысленных цитат.")
            return processed_quotes
        else:
            log("ERROR: GPT returned a non-list object. Fallback to empty.")
            return []

    except Exception as e:
        log(f"CRITICAL: GPT call or JSON parsing failed during quote processing: {e}")
        return []

# ────────────────────────────────────────────────────────────────────────────────
# Функции сбора данных и основная логика
# ────────────────────────────────────────────────────────────────────────────────

# Данные и ключи
NEWSAPI_KEY     = os.getenv("NEWSAPI_KEY")
YOUTUBE_KEY     = os.getenv("YOUTUBE_KEY")
MASTODON_TOKEN  = os.getenv("MASTODON_TOKEN")
MASTODON_HOST   = os.getenv("MASTODON_HOST", "mastodon.social")
USER_AGENT = "MomentumPulse/1.0 (+https://t.me/MomentumPulse)"
INFLUENCERS = [
    # Категория теперь используется только для первичного сбора, GPT примет финальное решение
    {"name": "Elon Musk",           "aliases": ["Elon Musk", "Musk"],           "category": "stock"},
    {"name": "Donald Trump",        "aliases": ["Donald Trump", "Trump"],       "category": "stock"},
    {"name": "Mark Zuckerberg",     "aliases": ["Mark Zuckerberg"],             "category": "stock"},
    {"name": "Jeff Bezos",          "aliases": ["Jeff Bezos"],                  "category": "stock"},
    {"name": "Bill Gates",          "aliases": ["Bill Gates"],                  "category": "stock"},
    {"name": "Warren Buffett",      "aliases": ["Warren Buffett", "Buffett"],   "category": "stock"},
    {"name": "Larry Fink",          "aliases": ["Larry Fink"],                  "category": "stock"},
    {"name": "Ross Ulbricht",       "aliases": ["Ross Ulbricht"],               "category": "crypto"},
    {"name": "Vitalik Buterin",     "aliases": ["Vitalik Buterin", "Buterin"],  "category": "crypto"},
    {"name": "Changpeng Zhao",      "aliases": ["Changpeng Zhao", "CZ"],        "category": "crypto"},
    {"name": "Michael Saylor",      "aliases": ["Michael Saylor"],              "category": "crypto"},
    {"name": "Anthony Pompliano",   "aliases": ["Anthony Pompliano"],           "category": "crypto"},
    {"name": "Balaji Srinivasan",   "aliases": ["Balaji Srinivasan", "Balaji"], "category": "crypto"},
]
LOOKBACK_HOURS = 24
MAX_QUOTES_PER_PERSON = 1
TIMEOUT = 12

def _clean_snippet(text: str, max_chars: int = 220) -> str:
    text = html.unescape(text).strip().replace("\n", " ")
    text = re.sub(r"\s{2,}", " ", text)
    sentences = re.split(r"(?<=[.!?])\s+", text)
    snippet = ""
    for sent in sentences:
        if len(snippet) + len(sent) <= max_chars:
            snippet = f"{snippet} {sent}".strip()
        else:
            break
    if not snippet:
        snippet = text[: max_chars].rsplit(" ", 1)[0] + "…"
    return snippet

# Функции _fetch_* остаются без изменений

def _fetch_reddit(alias: str) -> list[str]:
    url = (f"https://www.reddit.com/search.json?q=\"{requests.utils.quote(alias)}\"&sort=new&limit=10&restrict_sr=0&syntax=plain")
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        r.raise_for_status()
        posts = r.json().get("data", {}).get("children", [])
        out = []
        ts_limit = int((datetime.utcnow() - timedelta(hours=LOOKBACK_HOURS)).timestamp())
        for p in posts:
            data = p.get("data", {})
            if data.get("created_utc", 0) < ts_limit: continue
            body = data.get("selftext") or data.get("title", "")
            if body: out.append(_clean_snippet(body))
            if len(out) >= MAX_QUOTES_PER_PERSON: break
        return out
    except Exception as e:
        log(f"Reddit error ({alias}): {e}")
        return []

def _fetch_newsapi(alias: str) -> list[str]:
    if not NEWSAPI_KEY: return []
    url = "https://newsapi.org/v2/everything"
    params = {"qInTitle": alias, "sortBy": "publishedAt", "language": "en", "pageSize": 5, "apiKey": NEWSAPI_KEY}
    try:
        r = requests.get(url, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        news = r.json().get("articles", [])
        out = []
        ts_limit = datetime.utcnow() - timedelta(hours=LOOKBACK_HOURS)
        for n in news:
            published = n.get("publishedAt", "")[:19]
            try:
                if datetime.fromisoformat(published.replace("Z", "")) < ts_limit: continue
            except: pass
            out.append(_clean_snippet(n.get("title", "")))
            if len(out) >= MAX_QUOTES_PER_PERSON: break
        return out
    except Exception as e:
        log(f"NewsAPI error ({alias}): {e}")
        return []

def _fetch_youtube(alias: str) -> list[str]:
    if not YOUTUBE_KEY: return []
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {"part": "snippet", "q": alias, "maxResults": 5, "order": "date", "type": "video", "key": YOUTUBE_KEY}
    try:
        r = requests.get(url, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        items = r.json().get("items", [])
        out = []
        ts_limit = (datetime.utcnow() - timedelta(hours=LOOKBACK_HOURS))
        for it in items:
            sn = it.get("snippet", {})
            published = sn.get("publishedAt", "")[:19]
            try:
                if datetime.fromisoformat(published.replace("Z", "")) < ts_limit: continue
            except: pass
            title = sn.get("title", "")
            if title: out.append(_clean_snippet(title))
            if len(out) >= MAX_QUOTES_PER_PERSON: break
        return out
    except Exception as e:
        log(f"YouTube error ({alias}): {e}")
        return []

def _fetch_mastodon(alias: str) -> list[str]:
    if not MASTODON_TOKEN: return []
    url = f"https://{MASTODON_HOST}/api/v2/search"
    params = {"q": alias, "limit": 5, "resolve": "true"}
    headers = {"Authorization": f"Bearer {MASTODON_TOKEN}", "User-Agent": USER_AGENT}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
        r.raise_for_status()
        statuses = r.json().get("statuses", [])
        out = []
        ts_limit = (datetime.utcnow() - timedelta(hours=LOOKBACK_HOURS)).timestamp()
        for st in statuses:
            created = datetime.fromisoformat(st["created_at"][:-1])
            if created.timestamp() < ts_limit: continue
            text = re.sub("<.*?>", "", st["content"])
            out.append(_clean_snippet(text))
            if len(out) >= MAX_QUOTES_PER_PERSON: break
        return out
    except Exception as e:
        log(f"Mastodon error ({alias}): {e}")
        return []


SRC_FUNCS = [_fetch_reddit, _fetch_newsapi, _fetch_youtube, _fetch_mastodon]
def _collect_for_aliases(aliases: list[str]) -> list[str]:
    quotes = []
    for alias in aliases:
        for fn in SRC_FUNCS:
            quotes.extend(fn(alias))
            if len(quotes) >= MAX_QUOTES_PER_PERSON: break
        if len(quotes) >= MAX_QUOTES_PER_PERSON: break
    return [_clean_snippet(q) for q in quotes[:MAX_QUOTES_PER_PERSON]]

# --- Новая основная экспортируемая функция ---
def get_all_influencer_quotes() -> dict:
    """
    Собирает все цитаты, отправляет на обработку в GPT и возвращает
    два готовых текстовых блока: для крипто и фонды.
    """
    influencers_with_quotes = []
    raw_quotes = []

    # Шаг 1: Собираем все "сырые" цитаты в один список
    for inf in INFLUENCERS:
        q = _collect_for_aliases(inf["aliases"])
        if q:
            influencers_with_quotes.append(inf)
            raw_quotes.append(q[0])

    if not raw_quotes:
        return {"crypto": "", "stock": ""}

    # Шаг 2: Обрабатываем всё через GPT
    processed_quotes = _process_quotes_with_gpt(raw_quotes)

    # Шаг 3: Распределяем обработанные цитаты по категориям
    crypto_bullets = []
    stock_bullets = []

    for quote_data in processed_quotes:
        original_index = quote_data.get("original_index")
        theme = quote_data.get("theme")
        translated_quote = quote_data.get("translated_quote")

        # Индекс в JSON начинается с 1, в Python-списке с 0
        if original_index is not None and 1 <= original_index <= len(influencers_with_quotes):
            influencer_name = influencers_with_quotes[original_index - 1]["name"]
            bullet = f"— <b>{influencer_name}</b>: {translated_quote}"
            
            if theme == 'crypto':
                crypto_bullets.append(bullet)
            elif theme == 'stock':
                stock_bullets.append(bullet)

    # Шаг 4: Формируем финальные текстовые блоки
    crypto_block = ""
    if crypto_bullets:
        title = "🗣️ Мнения крипто-лидеров"
        crypto_block = "\n".join([title] + crypto_bullets)

    stock_block = ""
    if stock_bullets:
        title = "🗣️ Выдержки от людей, влияющих на фондовый рынок"
        stock_block = "\n".join([title] + stock_bullets)
        
    return {"crypto": crypto_block, "stock": stock_block}