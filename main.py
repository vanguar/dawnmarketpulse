#!/usr/bin/env python3
import os, sys, requests, openai
from datetime import datetime, timezone, date
from textwrap import wrap
from time import sleep

# ── ENV ─────────────────────────────────────────────────────────
openai.api_key = os.getenv("OPENAI_KEY")
TG_TOKEN  = os.getenv("TG_TOKEN")
CHAT_ID   = os.getenv("CHANNEL_ID")   # @name или -100…

MODEL       = "gpt-4o-mini"   # при желании gpt-4o
TIMEOUT     = 60
GPT_TOKENS  = 450             # ≈ 1 700-1 900 симв.
TG_LIMIT    = 4096            # лимит Telegram
CUT_LEN     = 3500            # запас от лимита

# ── PROMPT ──────────────────────────────────────────────────────
PROMPT = """
📈 Утренний обзор • {date}

Индексы 📊
• S&P 500, DAX, Nikkei, Nasdaq fut
→ Что это значит для инвестора?

Акции-лидеры 🚀 / Аутсайдеры 📉
• по 2–3 бумаги + причина
→ вывод.

Крипта ₿
• BTC, ETH + 3 альткоина → вывод.

Макро-новости 📰
• 3 заголовка + влияние

Цитаты дня 🗣
• до 2 цитат + смысл

Число-факт 🤔

⚡️ Идея дня — 2 предложения actionable-совета.

‼️ Без HTML/Markdown. Эмодзи разрешены. Максимум 1 600 символов.
"""

TG_URL = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"

# ── helpers ─────────────────────────────────────────────────────
def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S}] {msg}", flush=True)

def gpt_report() -> str:
    resp = openai.ChatCompletion.create(
        model=MODEL,
        messages=[{"role": "user", "content": PROMPT.format(date=date.today())}],
        timeout=TIMEOUT,
        temperature=0.4,
        max_tokens=GPT_TOKENS,
    )
    return resp.choices[0].message.content.strip()

def chunk(text: str, size: int = CUT_LEN):
    parts = wrap(text, width=size-50,              # ← запас 50 симв.
                 break_long_words=False,
                 break_on_hyphens=False)
    total = len(parts)
    if total == 1:
        return parts
    return [f"({i+1}/{total})\n{p}" for i, p in enumerate(parts)]

def send(part: str):
    r = requests.post(TG_URL, json={
        "chat_id": CHAT_ID,
        "text": part,
        "disable_web_page_preview": True
    }, timeout=10)
    if r.status_code != 200:
        log(f"TG {r.status_code}: {r.text}")

# ── main ────────────────────────────────────────────────────────
def main():
    try:
        for seg in chunk(gpt_report()):
            send(seg)
            sleep(1)           # пауза против flood-limit
        log("Posted OK.")
    except Exception as e:
        log(f"Fatal: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()


