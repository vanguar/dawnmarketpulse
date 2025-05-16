#!/usr/bin/env python3
"""
Daily market report → Telegram-канал.

Рабочий цикл (cron на Railway):
  1) Запрашивает отчёт у OpenAI.
  2) Делит, если >4096 символов.
  3) Постит в канал Markdown-V2.

ENV-переменные:
  OPENAI_KEY   – API-ключ OpenAI
  TG_TOKEN     – токен бота
  CHANNEL_ID   – @username канала или -100… ID
  TZ           – Europe/Berlin
"""

import os, sys, re, requests, openai
from datetime import datetime, timezone, date
from time import sleep

# ─── optional .env ───
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ─── конфиг ───
openai.api_key = os.getenv("OPENAI_KEY")
TG_TOKEN       = os.getenv("TG_TOKEN")
CHANNEL_ID     = os.getenv("CHANNEL_ID")

MODEL          = "gpt-4o-mini"     # меняй на "gpt-4o" если нужно
RETRIES        = 3
TIMEOUT        = 60
MAX_TG_LEN     = 4096

USER_PROMPT = (
    "Утренний обзор рынков на {date} (пиши по-русски).\n"
    "Включи:\n"
    "• Как закрылись основные индексы (S&P 500 фьючерсы, DAX, Nikkei и т.д.).\n"
    "• Топ-движения акций (основные рост / падение).\n"
    "• Изменения Bitcoin, Ethereum и пяти крупнейших альткоинов.\n"
    "• Ключевые макро-новости, способные повлиять на рынок сегодня.\n"
    "• Короткие цитаты/твиты влиятельных фигур (Илон Маск, Сэм Олтман, чиновники ФРС) + однострочная интерпретация.\n"
    "• Заверши одним «числом-фактом» для размышлений.\n\n"
    "Выводи сжатым Markdown-V2 бюллетенем, ≤ 400 слов."
)

# ─── helpers ───
MD_V2_ESC = re.compile(r'([_*[\]()~`>#+\-=|{}.!\\])')
def escape_md(text: str) -> str:
    """Экранирует спец-символы Telegram MarkdownV2."""
    return MD_V2_ESC.sub(r'\\\1', text)

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
    parts, chunk, length = [], [], 0
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
        part = escape_md(part)
        r = requests.post(url, json={
            "chat_id": CHANNEL_ID,
            "text": part,
            "parse_mode": "MarkdownV2",
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
