#!/usr/bin/env python3
import os, sys, requests, openai
from datetime import datetime, timezone, date
from textwrap import wrap
from time import sleep

openai.api_key = os.getenv("OPENAI_KEY")
TG_TOKEN       = os.getenv("TG_TOKEN")
CHANNEL_ID     = os.getenv("CHANNEL_ID")

MODEL       = "gpt-4o-mini"
TIMEOUT     = 60
TG_LIMIT    = 4096          # технический лимит Telegram
GPT_TOKENS  = 400           # ~1 600–1 800 символов

PROMPT = """
📈 Утренний обзор • {date}

Индексы 📊
• S&P 500, DAX, Nikkei, Nasdaq fut
→ Что это значит для инвестора?

Акции-лидеры 🚀 / Аутсайдеры 📉
• по 2–3 бумаги + причина
→ Вывод.

Крипта ₿
• BTC, ETH + 3 альткоина
→ Вывод.

Макро-новости 📰
• 3 главных заголовка + влияние

Цитаты дня 🗣
• до 2 цитат + смысл

Число-факт 🤔

⚡️ Идея дня – 2 предложения actionable-совета.

‼️ Только обычный текст, без HTML. Максимум 1 600 символов.
"""

def log(msg):
    print(f"[{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC] {msg}", flush=True)

def gpt_report():
    r = openai.ChatCompletion.create(
        model=MODEL,
        messages=[{"role": "user", "content": PROMPT.format(date=date.today())}],
        timeout=TIMEOUT,
        temperature=0.4,
        max_tokens=GPT_TOKENS,
    )
    return r.choices[0].message.content.strip()

def chunk(text, limit=TG_LIMIT):
    parts = wrap(text, width=limit-20, break_long_words=False, break_on_hyphens=False)
    total = len(parts)
    return [f"({i+1}/{total})\n{p}" if total > 1 else p for i, p in enumerate(parts)]

def send(text):
    for part in chunk(text):
        r = requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": CHANNEL_ID, "text": part, "disable_web_page_preview": True},
            timeout=10
        )
        if r.status_code != 200:
            log(f"TG error {r.status_code}: {r.text}")
        sleep(1)

def main():
    try:
        send(gpt_report())
        log("Posted OK.")
    except Exception as e:
        log(f"Fatal: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()


