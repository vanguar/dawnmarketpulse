# influencer_quotes_reader.py
# v2.0 – 10-Jun-2025
#
# Забираем свежие высказывания инфлюенсеров и используем GPT для качественного перевода.
# Изменение v2.0: Полный отказ от googletrans в пользу пакетного перевода через OpenAI GPT.

import os
import time
import html
import re
import requests
import openai
from datetime import datetime, timedelta
from custom_logger import log

# --- Конфигурация GPT ---
# Используем ту же модель, что и в main.py для консистентности
GPT_MODEL_FOR_TRANSLATION = "gpt-4o-mini"


def _translate_quotes_with_gpt(quotes: list[str]) -> list[str]:
    """
    Отправляет список цитат в GPT для качественного "органического" перевода и адаптации.
    Возвращает список переведенных цитат.
    """
    if not quotes:
        return []

    # Создаем нумерованный список цитат для промпта
    numbered_quotes = "\n".join([f'{i+1}. "{quote}"' for i, quote in enumerate(quotes)])

    prompt = f"""
Ты — профессиональный редактор и переводчик для популярного финансового Telegram-канала. Тебе предоставлен список сырых цитат и высказываний на английском языке.
Твоя задача — выполнить качественный, "органический" перевод-адаптацию этих цитат на русский язык.

Ключевые требования:
1.  **Естественность и плавность:** Перевод должен звучать как живая, естественная русская речь, а не как дословный машинный перевод. Смело адаптируй фразы и обороты, сохраняя исходный смысл и тон.
2.  **Контекст:** Учитывай, что это мнения лидеров в сфере финансов, технологий и криптовалют. Терминологию используй правильно.
3.  **Точность:** Не теряй ключевые детали, цифры и основной посыл оригинального высказывания.
4.  **Формат ответа:** Верни ТОЛЬКО переведенные цитаты в виде нумерованного списка. Порядок должен строго соответствовать оригиналу. Не добавляй ничего лишнего: ни заголовков, ни комментариев, ни своих мыслей.

Оригинальные цитаты для перевода:
---
{numbered_quotes}
---

Твой адаптированный перевод (строго нумерованный список):
"""

    try:
        # Проверяем, установлен ли ключ OpenAI, который настраивается в main.py
        if not openai.api_key:
            log("CRITICAL: OpenAI API key is not set. Cannot perform translation.")
            return quotes # Возвращаем сырые цитаты, если ключ не найден

        log(f"INFO: Отправка {len(quotes)} цитат в GPT для перевода...")
        response = openai.ChatCompletion.create(
            model=GPT_MODEL_FOR_TRANSLATION,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6,  # Немного креативности для лучшего стиля
            max_tokens=2048   # Запас токенов для перевода
        )
        translated_text = response.choices[0].message.content.strip()

        # Парсим нумерованный список из ответа GPT
        translated_quotes_list = re.findall(r"^\d+\.\s*\"?(.*?)\"?$", translated_text, re.MULTILINE)

        if len(translated_quotes_list) == len(quotes):
            log("INFO: GPT успешно перевел и адаптировал все цитаты.")
            return translated_quotes_list
        else:
            log(f"ERROR: GPT translation parsing failed. Expected {len(quotes)} quotes, got {len(translated_quotes_list)}. Returning raw quotes.")
            return quotes  # Возврат к сырым данным при ошибке парсинга

    except Exception as e:
        log(f"CRITICAL: OpenAI API call failed during translation: {e}")
        return quotes  # Возврат к сырым данным при ошибке API

# ────────────────────────────────────────────────────────────────────────────────
# Остальная часть файла без изменений в логике сбора, только интеграция с новой функцией перевода
# ────────────────────────────────────────────────────────────────────────────────


# 1. Данные и ключи
NEWSAPI_KEY     = os.getenv("NEWSAPI_KEY")
YOUTUBE_KEY     = os.getenv("YOUTUBE_KEY")
MASTODON_TOKEN  = os.getenv("MASTODON_TOKEN")
MASTODON_HOST   = os.getenv("MASTODON_HOST", "mastodon.social")
USER_AGENT = "MomentumPulse/1.0 (+https://t.me/MomentumPulse)"
INFLUENCERS = [
    # category: crypto | stock
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

# 2. Хелперы
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
_cut = _clean_snippet

# 3. Функции сбора данных (без изменений)
def _fetch_reddit(alias: str) -> list[str]:
    url = (
        f"https://www.reddit.com/search.json?q=\"{requests.utils.quote(alias)}\""
        f"&sort=new&limit=10&restrict_sr=0&syntax=plain"
    )
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        r.raise_for_status()
        posts = r.json().get("data", {}).get("children", [])
        out = []
        ts_limit = int((datetime.utcnow() - timedelta(hours=LOOKBACK_HOURS)).timestamp())
        for p in posts:
            data = p.get("data", {})
            if data.get("created_utc", 0) < ts_limit:
                continue
            body = data.get("selftext") or data.get("title", "")
            if body:
                out.append(_cut(body))
            if len(out) >= MAX_QUOTES_PER_PERSON:
                break
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
                if datetime.fromisoformat(published.replace("Z", "")) < ts_limit:
                    continue
            except: pass
            out.append(_cut(n.get("title", "")))
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
                if datetime.fromisoformat(published.replace("Z", "")) < ts_limit:
                    continue
            except: pass
            title = sn.get("title", "")
            if title:
                out.append(_cut(title))
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
            out.append(_cut(text))
            if len(out) >= MAX_QUOTES_PER_PERSON: break
        return out
    except Exception as e:
        log(f"Mastodon error ({alias}): {e}")
        return []

# 4. Агрегация и пакетный перевод
SRC_FUNCS = [_fetch_reddit, _fetch_newsapi, _fetch_youtube, _fetch_mastodon]
def _collect_for_aliases(aliases: list[str]) -> list[str]:
    quotes = []
    for alias in aliases:
        for fn in SRC_FUNCS:
            quotes.extend(fn(alias))
            if len(quotes) >= MAX_QUOTES_PER_PERSON: break
        if len(quotes) >= MAX_QUOTES_PER_PERSON: break
    return [_clean_snippet(q) for q in quotes[:MAX_QUOTES_PER_PERSON]]

def _build_block(category: str) -> str:
    influencers_with_quotes = []
    raw_quotes_to_translate = []

    # Шаг 1: Собираем все "сырые" цитаты в один список
    for inf in INFLUENCERS:
        if inf["category"] != category:
            continue
        q = _collect_for_aliases(inf["aliases"])
        if q:
            influencers_with_quotes.append(inf)
            raw_quotes_to_translate.append(q[0])

    if not raw_quotes_to_translate:
        return ""

    # Шаг 2: Переводим все цитаты одним пакетным запросом к GPT
    translated_quotes = _translate_quotes_with_gpt(raw_quotes_to_translate)

    # Шаг 3: Собираем итоговый блок с переведенными цитатами
    bullets = []
    if len(translated_quotes) == len(influencers_with_quotes):
        for inf, translated_q in zip(influencers_with_quotes, translated_quotes):
            bullets.append(f"— <b>{inf['name']}</b>: {translated_q}")
    else:
        # План Б: если что-то пошло не так, выводим что есть (например, сырые цитаты)
        log("ERROR: Mismatch in translated quotes count. Falling back to raw quotes.")
        for inf, raw_q in zip(influencers_with_quotes, raw_quotes_to_translate):
            bullets.append(f"— <b>{inf['name']}</b>: {raw_q} (ошибка перевода)")

    if not bullets:
        return ""

    title = "🗣️ Мнения крипто-лидеров" if category == "crypto" \
            else "🗣️ Выдержки от людей, влияющих на фондовый рынок"
    return "\n".join([title] + bullets)

# Экспортируемые функции
def get_crypto_quotes_block() -> str:
    return _build_block("crypto")

def get_stock_quotes_block() -> str:
    return _build_block("stock")