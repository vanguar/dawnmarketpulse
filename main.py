#!/usr/bin/env python3
import os, sys, requests, openai
from datetime import datetime, timezone, date
from textwrap import wrap
from time import sleep

# ── ENV ─────────────────────────────────────────────────────────
openai.api_key = os.getenv("OPENAI_KEY")
TG_TOKEN   = os.getenv("TG_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")          # @username или -100…

MODEL       = "gpt-4o-mini"                   # при желании gpt-4o
TIMEOUT     = 60
GPT_TOKENS  = 450                             # ≈ 1 700–1 900 симв.
TG_LIMIT    = 4096                            # жёсткий лимит Telegram
CHUNK_SIZE  = 3500                            # безопасное «окно» для резки

# ── PROMPT ──────────────────────────────────────────────────────
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
→ Короткий вывод.

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
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")
    print(f"[{ts}] {msg}", flush=True)

def get_report() -> str:
    resp = openai.ChatCompletion.create(
        model=MODEL,
        messages=[{"role": "user", "content": PROMPT.format(date=date.today())}],
        timeout=TIMEOUT,
        temperature=0.4,
        max_tokens=GPT_TOKENS,
    )
    return resp.choices[0].message.content.strip()

def chunk_text(text: str, limit: int = CHUNK_SIZE):
    """Делим по строкам, чтобы сохранить абзацы и не превысить limit."""
    if len(text) <= limit:
        return [text]

    parts, buf, length = [], [], 0
    for line in text.splitlines(keepends=True):
        if length + len(line) > limit:
            parts.append("".join(buf).rstrip())
            buf, length = [], 0
        buf.append(line)
        length += len(line)
    if buf:
        parts.append("".join(buf).rstrip())

    total = len(parts)
    return [f"({i+1}/{total})\n{p}" if total > 1 else p
            for i, p in enumerate(parts)]

def send(part: str):
    if not part.strip():
        log("Empty segment skipped.")
        return
    try:
        r = requests.post(
            TG_URL,
            json={"chat_id": CHANNEL_ID, "text": part, "disable_web_page_preview": True},
            timeout=10
        )
        r.raise_for_status()
    except requests.exceptions.RequestException as e:
        log(f"Telegram error: {e}")

# ── main ────────────────────────────────────────────────────────
def main():
    try:
        report = get_report()
        for seg in chunk_text(report):
            send(seg)
            sleep(1)                       # анти-флуд
        log("Posted OK.")
    except openai.error.OpenAIError as e:
        log(f"OpenAI API error: {e}")
        sys.exit(1)
    except Exception as e:
        log(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

