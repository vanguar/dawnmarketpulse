#!/usr/bin/env python3
"""
Daily market report → Telegram-канал.
Cron-время: 07:05 UTC ≈ 09:05 Europe/Kyiv (настраивается в railway.json).

ENV-переменные (в Railway):
  OPENAI_KEY   – ключ OpenAI
  TG_TOKEN     – токен Telegram-бота
  CHANNEL_ID   – @username канала ИЛИ -100… ID
  TZ           – Europe/Berlin
"""

import os, sys, requests, openai
from datetime import datetime, timezone, date

# ── ENV ─────────────────────────────────────────────────────────
openai.api_key = os.getenv("OPENAI_KEY")
TG_TOKEN       = os.getenv("TG_TOKEN")
CHANNEL_ID     = os.getenv("CHANNEL_ID")

MODEL        = "gpt-4o-mini"   # можно 'gpt-4o'
TIMEOUT      = 60              # сек
MAX_TOKENS   = 350             # ≈ 1 500 символов

# ── PROMPT ──────────────────────────────────────────────────────
PROMPT = """
📈 Утренний обзор • {date}

Индексы 📊
• S&P 500, DAX, Nikkei, Nasdaq fut
→ Одной строкой: Что это значит для инвестора?

Акции-лидеры 🚀 / Аутсайдеры 📉
• по 2–3 бумаги + краткая причина движения
→ Вывод для инвестора.

Крипта ₿
• BTC, ETH + 3 ярких альткоина (цена и %)
→ Короткий вывод.

Макро-новости 📰
• три заголовка + влияние на рынок

Цитаты дня 🗣
• до 3 цитат + смысл для рынка

Число-факт 🤔

⚡️ Идея дня
• 2–3 предложения actionable-совета.

‼️ Пиши **только** обычный текст (без HTML/Markdown).  
‼️ Итоговый объём ≤ 1 500 символов.
"""

# ── helpers ─────────────────────────────────────────────────────
def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    print(f"[{ts}] {msg}", flush=True)

def get_report() -> str:
    prompt = PROMPT.format(date=date.today().isoformat())
    resp = openai.ChatCompletion.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        timeout=TIMEOUT,
        temperature=0.4,
        max_tokens=MAX_TOKENS
    )
    return resp.choices[0].message.content.strip()

def post_to_tg(text: str) -> None:
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    r = requests.post(url, json={
        "chat_id": CHANNEL_ID,
        "text": text,
        "disable_web_page_preview": True
    }, timeout=10)
    if r.status_code != 200:
        log(f"Telegram error {r.status_code}: {r.text}")

# ── main ───────────────────────────────────────────────────────
def main() -> None:
    try:
        report = get_report()
        post_to_tg(report)
        log("Posted OK.")
    except Exception as e:
        log(f"Fatal: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

