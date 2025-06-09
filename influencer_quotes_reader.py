# influencer_quotes_reader.py
# v1.0 – 09-Jun-2025
#
# Забираем свежие высказывания инфлюенсеров из Reddit, NewsAPI, YouTube и Mastodon
# без платного Twitter API.  Всё «read-only», без Selenium.

import os, time, html, re, requests
from datetime import datetime, timedelta
from custom_logger import log     # уже есть в проекте
from googletrans import Translator
translator = Translator()

def _ru(text: str) -> str:
    """Переводит цитату на русский, если исходник не ru/uk."""
    try:
        tr = translator.translate(text, dest="ru")
        return tr.text
    except Exception as e:
        log(f"Translate error: {e}")
        return text


# ────────────────────────────────────────────────────────────────────────────────
# 1. Данные и ключи

NEWSAPI_KEY     = os.getenv("NEWSAPI_KEY")     # https://newsapi.org
YOUTUBE_KEY     = os.getenv("YOUTUBE_KEY")     # console.cloud.google.com
MASTODON_TOKEN  = os.getenv("MASTODON_TOKEN")  # любой публичный инстанс
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

LOOKBACK_HOURS = 24          # берём только за последние сутки
MAX_QUOTES_PER_PERSON = 1    # лишнее не нужно – отчёт и так длинный
TIMEOUT = 12


# ────────────────────────────────────────────────────────────────────────────────
# 2. Хелперы

def _cut(text: str, n: int = 140) -> str:
    text = html.unescape(text.strip().replace('\n', ' '))
    return (text[:n] + "…") if len(text) > n else text

def _to_ts(dt: datetime) -> int:
    return int(dt.replace(tzinfo=None).timestamp())

def _since_param(hours_back: int = LOOKBACK_HOURS):
    t = datetime.utcnow() - timedelta(hours=hours_back)
    return _to_ts(t)


# ────────────────────────────────────────────────────────────────────────────────
# 3.   Reddit  (без auth – достаточно для поиска)

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
        ts_limit = _since_param()
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


# ────────────────────────────────────────────────────────────────────────────────
# 4.   NewsAPI

def _fetch_newsapi(alias: str) -> list[str]:
    if not NEWSAPI_KEY:
        return []
    url = "https://newsapi.org/v2/everything"
    params = {
        "qInTitle": alias,
        "sortBy": "publishedAt",
        "language": "en",
        "pageSize": 5,
        "apiKey": NEWSAPI_KEY,
    }
    try:
        r = requests.get(url, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        news = r.json().get("articles", [])
        out = []
        ts_limit = datetime.utcnow() - timedelta(hours=LOOKBACK_HOURS)
        for n in news:
            published = n.get("publishedAt", "")[:19]  # 2025-06-09T08:05:00Z
            try:
                if datetime.fromisoformat(published.replace("Z", "")) < ts_limit:
                    continue
            except:  # парсеру насрать
                pass
            out.append(_cut(n.get("title", "")))
            if len(out) >= MAX_QUOTES_PER_PERSON:
                break
        return out
    except Exception as e:
        log(f"NewsAPI error ({alias}): {e}")
        return []


# ────────────────────────────────────────────────────────────────────────────────
# 5.   YouTube (title + description новых видео)

def _fetch_youtube(alias: str) -> list[str]:
    if not YOUTUBE_KEY:
        return []
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": alias,
        "maxResults": 5,
        "order": "date",
        "type": "video",
        "key": YOUTUBE_KEY,
    }
    try:
        r = requests.get(url, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        items = r.json().get("items", [])
        out = []
        ts_limit = _since_param()
        for it in items:
            sn = it.get("snippet", {})
            published = sn.get("publishedAt", "")[:19]
            try:
                if datetime.fromisoformat(published.replace("Z", "")) < datetime.utcfromtimestamp(ts_limit):
                    continue
            except:
                pass
            title = sn.get("title", "")
            if title:
                out.append(_cut(title))
            if len(out) >= MAX_QUOTES_PER_PERSON:
                break
        return out
    except Exception as e:
        log(f"YouTube error ({alias}): {e}")
        return []


# ────────────────────────────────────────────────────────────────────────────────
# 6.   Mastodon  (поиск по публичному /api/v2/search)

def _fetch_mastodon(alias: str) -> list[str]:
    if not MASTODON_TOKEN:
        return []
    url = f"https://{MASTODON_HOST}/api/v2/search"
    params = {"q": alias, "limit": 5, "resolve": "true"}
    headers = {"Authorization": f"Bearer {MASTODON_TOKEN}", "User-Agent": USER_AGENT}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
        r.raise_for_status()
        statuses = r.json().get("statuses", [])
        out = []
        ts_limit = _since_param()
        for st in statuses:
            created = datetime.fromisoformat(st["created_at"][:-1])
            if created.timestamp() < ts_limit:
                continue
            # убираем html-теги
            text = re.sub("<.*?>", "", st["content"])
            out.append(_cut(text))
            if len(out) >= MAX_QUOTES_PER_PERSON:
                break
        return out
    except Exception as e:
        log(f"Mastodon error ({alias}): {e}")
        return []


# ────────────────────────────────────────────────────────────────────────────────
# 7.   Агрегация

SRC_FUNCS = [_fetch_reddit, _fetch_newsapi, _fetch_youtube, _fetch_mastodon]

def _collect_for_aliases(aliases: list[str]) -> list[str]:
    quotes = []
    for alias in aliases:
        for fn in SRC_FUNCS:
            quotes.extend(fn(alias))
            if len(quotes) >= MAX_QUOTES_PER_PERSON:
                break
        if len(quotes) >= MAX_QUOTES_PER_PERSON:
            break
    # Переводим и обрезаем до нужного количества
    return [_ru(q) for q in quotes[:MAX_QUOTES_PER_PERSON]]


def _build_block(category: str) -> str:
    bullets = []
    for inf in INFLUENCERS:
        if inf["category"] != category:
            continue
        q = _collect_for_aliases(inf["aliases"])
        if q:
            bullets.append(f"— <b>{inf['name']}</b>: {q[0]}")
    if not bullets:
        return ""
    title = "🗣️ Мнения крипто-лидеров" if category == "crypto" \
            else "🗣️ Выдержки от людей, влияющих на фондовый рынок"
    return "\n".join([title] + bullets)

# Экспортируемые функции  ───────────────────────────────────────────────────────
def get_crypto_quotes_block() -> str:
    return _build_block("crypto")

def get_stock_quotes_block() -> str:
    return _build_block("stock")
