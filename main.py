#!/usr/bin/env python3
"""
Daily market report → Telegram-канал.

Запускается по крону на Railway:
  1) Запрашивает отчёт у OpenAI.
  2) Делит, если >4096 симв.
  3) Шлёт в канал.

ENV (на Railway / в .env):
  OPENAI_KEY   — API-ключ OpenAI
  TG_TOKEN     — токен бота
  CHANNEL_ID   — @username канала или -100… ID
  TZ           — Europe/Berlin
"""

import os, sys, requests, openai
from datetime import datetime, timezone, date
from time import sleep

# ─── optional: локальный .env ───
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv не обязателен в проде

# ─── конфиг ───
openai.api_key = os.getenv("OPENAI_KEY")
TG_TOKEN       = os.getenv("TG_TOKEN")
CHANNEL_ID     = os.getenv("CHANNEL_ID")

MODEL          = "gpt-4o"
RETRIES        = 3
TIMEOUT        = 60
MAX_TG_LEN     = 4096

USER_PROMPT = (
    "Morning market report for {date}.\n"
    "Include:\n"
    "• Overnight performance of key equity indices (S&P 500 futures, DAX, Nikkei).\n"
    "• Biggest stock movers (top gainers / losers).\n"
    "• Bitcoin, Ethereum and top-5 altcoins moves.\n"
    "• Major macro headlines likely to move markets today.\n"
    "• Short quotes or tweets from influential figures (e.g. Elon Musk, Sam Altman, Fed officials) with a one-line interpretation.\n"
    "• Finish with one quirky “food-for-thought” stat.\n\n"
    "Output as a concise Markdown bulletin, max 400 words."
)

# ─── helpers ───
def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    print(f"[{ts}] {msg}", flush=True)

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
                max_tokens=600
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            log(f"OpenAI error: {e}")
            if n == RETRIES:
                raise
            sleep(2 ** n)

def split_long(text: str) -> list[str]:
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

def post_to_tg(text: str) -> None:
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    for part in split_long(text):
        r = requests.post(url, json={
            "chat_id": CHANNEL_ID,
            "text": part,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }, timeout=10)
        if r.status_code != 200:
            log(f"Telegram error {r.status_code}: {r.text}")
        sleep(1)

# ─── main ───
def main() -> None:
    try:
        report = get_report()
        post_to_tg(report)
        log("Posted OK.")
    except Exception as err:
        log(f"Fatal: {err}")
        sys.exit(1)

if __name__ == "__main__":
    main()
