#!/usr/bin/env python3
import os, sys, requests, openai
from datetime import datetime, timezone, date

openai.api_key = os.getenv("OPENAI_KEY")
TG_TOKEN  = os.getenv("TG_TOKEN")
CHAT_ID   = os.getenv("CHANNEL_ID")   # @name или -100…

MODEL      = "gpt-4o-mini"
TIMEOUT    = 60
GPT_TOKENS = 450          # ≈ 1800-2000 символов
CUT_LEN    = 3500         # надёжно < 4096

PROMPT = f"""
📈 Утренний обзор • {{date}}

Индексы 📊
• S&P 500, DAX, Nikkei, Nasdaq fut
→ Что это значит для инвестора?

Акции-лидеры 🚀 / Аутсайдеры 📉
• по 2–3 бумаги + причина → вывод

Крипта ₿
• BTC, ETH + 3 альткоина → вывод

Макро-новости 📰
• 3 заголовка + влияние

Цитаты дня 🗣
• до 2 цитат + смысл

Число-факт 🤔

⚡️ Идея дня — 2 предложения совета

‼️ Только обычный текст, без HTML/Markdown. ≤ 2 000 символов.
"""

TG_URL = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"

def log(msg):
    print(f"[{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S}] {msg}", flush=True)

def gpt():
    txt = openai.ChatCompletion.create(
        model=MODEL,
        messages=[{"role": "user", "content": PROMPT.format(date=date.today())}],
        timeout=TIMEOUT,
        temperature=0.4,
        max_tokens=GPT_TOKENS).choices[0].message.content.strip()
    return txt

def chunks(text, size=CUT_LEN):
    parts = [text[i:i+size] for i in range(0, len(text), size)]
    if len(parts) == 1:                      # всё влезло
        return parts
    total = len(parts)
    return [f"({n+1}/{total})\n{p}" for n, p in enumerate(parts)]

def send(msg):
    r = requests.post(TG_URL, json={
        "chat_id": CHAT_ID,
        "text": msg,
        "disable_web_page_preview": True})
    if r.status_code != 200:
        log(f"TG {r.status_code}: {r.text}")

def main():
    try:
        for part in chunks(gpt()):
            send(part)
        log("Posted OK.")
    except Exception as e:
        log(f"Fatal: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()



