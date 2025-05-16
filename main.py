#!/usr/bin/env python3
import os, sys, requests, openai
from datetime import datetime, timezone, date
from time import sleep

openai.api_key = os.getenv("OPENAI_KEY")
TG_TOKEN       = os.getenv("TG_TOKEN")
CHANNEL_ID     = os.getenv("CHANNEL_ID")

MODEL   = "gpt-4o-mini"
TIMEOUT = 60

PROMPT = """
📈 Утренний обзор • {date}

Индексы 📊
• S&P 500, DAX, Nikkei, Nasdaq fut  
→ Что это значит для инвестора?

Акции-лидеры 🚀 / Аутсайдеры 📉
• по 2-3 бумаги с кротким пояснением  
→ Вывод для инвестора.

Крипта ₿
• BTC, ETH + 3 альткоина (ценa и %)  
→ Вывод.

Макро-новости 📰
• три заголовка + краткое влияние

Цитаты дня 🗣
• до 3 цитат + одно-строчный смысл

Число-факт 🤔

⚡️ Идея дня
• 2-3 предложения actionable-совета.

‼️ Только обычный текст, без **каких-либо** HTML/Markdown тегов! Максимум 1500 символов.
"""

def log(msg): print(f"[{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC] {msg}", flush=True)

def get_report():
    prompt = PROMPT.format(date=date.today().isoformat())
    r = openai.ChatCompletion.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        timeout=TIMEOUT,
        temperature=0.4,
        max_tokens=350      # ≈ 1500 символов
    )
    return r.choices[0].message.content.strip()

def post(text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    r = requests.post(url, json={"chat_id": CHANNEL_ID, "text": text, "disable_web_page_preview": True}, timeout=10)
    if r.status_code != 200:
        log(f"Telegram error {r.status_code}: {r.text}")

def main():
    try:
        post(get_report())
        log("Posted OK.")
    except Exception as e:
        log(f"Fatal: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()


