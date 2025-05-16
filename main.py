#!/usr/bin/env python3
import os, sys, requests, openai
from datetime import datetime, timezone, date
from time import sleep

openai.api_key = os.getenv("OPENAI_KEY")
TG_TOKEN       = os.getenv("TG_TOKEN")
CHANNEL_ID     = os.getenv("CHANNEL_ID")

MODEL       = "gpt-4o-mini"
TIMEOUT     = 60
MAX_TOKENS  = 450            # ≈ 1900–2000 символов
TG_LIMIT    = 4096           # лимит одного поста

PROMPT = """
📈 Утренний обзор • {date}

Индексы 📊
• S&P 500, DAX, Nikkei, Nasdaq fut
→ Что это значит для инвестора?

Акции-лидеры 🚀 / Аутсайдеры 📉
• по 2–3 бумаги + причина
→ Вывод.

Крипта ₿
• BTC, ETH + 3 альткоина (цена и %)
→ Короткий вывод.

Макро-новости 📰
• 3 заголовка + влияние

Цитаты дня 🗣
• до 3 цитат + смысл

Число-факт 🤔

⚡️ Идея дня
• 2–3 предложения actionable-совета.

Только обычный текст (без HTML/Markdown). Объём ~2000 символов максимум.
"""

def log(msg):
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    print(f"[{ts}] {msg}", flush=True)

def get_report():
    prompt = PROMPT.format(date=date.today().isoformat())
    r = openai.ChatCompletion.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        timeout=TIMEOUT,
        temperature=0.4,
        max_tokens=MAX_TOKENS,
    )
    return r.choices[0].message.content.strip()

def split_long(text: str):
    """Режем по абзацам, чтобы каждый кусок ≤ TG_LIMIT."""
    if len(text) <= TG_LIMIT:
        return [text]
    parts, chunk, length = [], [], 0
    for p in text.split("\n\n"):
        p += "\n\n"
        if length + len(p) > TG_LIMIT:
            parts.append(''.join(chunk).rstrip())
            chunk, length = [], 0
        chunk.append(p)
        length += len(p)
    if chunk:
        parts.append(''.join(chunk).rstrip())
    # добавляем маркеры (1/3)
    total = len(parts)
    return [f"({i+1}/{total})\n{part}" for i, part in enumerate(parts)]

def post_to_tg(text: str):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    for part in split_long(text):
        r = requests.post(url, json={
            "chat_id": CHANNEL_ID,
            "text": part,
            "disable_web_page_preview": True
        }, timeout=10)
        if r.status_code != 200:
            log(f"Telegram error {r.status_code}: {r.text}")
        sleep(1)

def main():
    try:
        post_to_tg(get_report())
        log("Posted OK.")
    except Exception as e:
        log(f"Fatal: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()


