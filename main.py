#!/usr/bin/env python3
"""
Daily market report → Telegram-канал
Cron: 07:05 UTC ≈ 09:05 Europe/Kyiv (см. railway.json)
"""

import os, sys, html, requests, openai
from datetime import datetime, timezone, date
from time import sleep

# ─── ENV ────────────────────────────────────────────────────────────────────────
openai.api_key = os.getenv("OPENAI_KEY")
TG_TOKEN       = os.getenv("TG_TOKEN")
CHANNEL_ID     = os.getenv("CHANNEL_ID")

MODEL          = "gpt-4o-mini"         # или "gpt-4o"
RETRIES        = 3
TIMEOUT        = 60
MAX_TG_LEN     = 4096                  # лимит Telegram

# ─── PROMPT ─────────────────────────────────────────────────────────────────────
USER_PROMPT = """
Сформируй углублённый утренний обзор рынков на {date}.
Верни текст сразу в Telegram-HTML (разрешены только<b>,<i>,<u>,<s>,<code>,<a>).
Структура:

<b>📈 Утренний обзор • {date}</b>
<b>Индексы 📊</b>
• S&P 500, DAX, Nikkei, Nasdaq fut → + одна строка: Что это значит для инвестора?

<b>Акции-лидеры 🚀 / Аутсайдеры 📉</b>
• по 2–3 бумаги в каждом подблоке, затем вывод.

<b>Крипто ₿</b>
• BTC, ETH + 3 альткоина, затем вывод.

<b>Макро-новости 📰</b>
• три пункта + расшифровка влияния.

<b>Цитаты дня 🗣</b>
• до 3 цитат с краткой интерпретацией.

<b>Число-факт 🤔</b>
<b>⚡️ Идея дня</b> — 2-3 предложения actionable-совета.

Требования:
• Тон дружелюбный, но профессиональный. Без Markdown-символов.  
• Максимум 450 слов.
"""

# ─── helpers ───────────────────────────────────────────────────────────────────
def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    print(f"[{ts}] {msg}", flush=True)

def safe_html(text: str) -> str:
    """Экранируем &, <, > чтобы Telegram-HTML не сломался."""
    return html.escape(text, quote=False).replace("&amp;nbsp;", " ")

def get_report() -> str:
    prompt = USER_PROMPT.format(date=date.today().isoformat())
    for n in range(1, RETRIES + 1):
        try:
            log(f"OpenAI try {n}")
            resp = openai.ChatCompletion.create(
                model=MODEL,
                timeout=TIMEOUT,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
                max_tokens=700,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            log(f"OpenAI error: {e}")
            if n == RETRIES:
                raise
            sleep(2 ** n)

def split_long(text: str):
    if len(text) <= MAX_TG_LEN:
        return [text]
    parts, chunk = [], []
    length = 0
    for line in text.splitlines(True):
        if length + len(line) > MAX_TG_LEN:
            parts.append(''.join(chunk))
            chunk, length = [], 0
        chunk.append(line)
        length += len(line)
    if chunk:
        parts.append(''.join(chunk))
    return parts

def post_to_tg(text: str):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    for part in split_long(text):
        part = safe_html(part)
        r = requests.post(url, json={
            "chat_id": CHANNEL_ID,
            "text": part,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }, timeout=10)
        if r.status_code != 200:
            log(f"Telegram error {r.status_code}: {r.text}")
        sleep(1)

# ─── main ──────────────────────────────────────────────────────────────────────
def main():
    try:
        report = get_report()
        post_to_tg(report)
        log("Posted OK.")
    except Exception as err:
        log(f"Fatal: {err}")
        sys.exit(1)

if __name__ == "__main__":
    main()


