#!/usr/bin/env python3
"""
Daily market report → Telegram-канал.
Запускается по крону (Railway railway.json) — 07:05 UTC ≈ 09:05 Europe/Kyiv.
"""

import os, sys, re, requests, openai
from datetime import datetime, timezone, date
from time import sleep

# ── optional .env ────────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── env-параметры ───────────────────────────────────────────────────────────────
openai.api_key = os.getenv("OPENAI_KEY")
TG_TOKEN       = os.getenv("TG_TOKEN")
CHANNEL_ID     = os.getenv("CHANNEL_ID")

MODEL          = "gpt-4o-mini"   # при желании замени на "gpt-4o"
RETRIES        = 3
TIMEOUT        = 60
MAX_TG_LEN     = 4096

# ── промпт ──────────────────────────────────────────────────────────────────────
USER_PROMPT = """
Сформируй **углублённый** утренний обзор рынков на {date} — исключительно на русском и сразу в Telegram MarkdownV2.

❗️Требования к стилю:
• Тон дружелюбный, но профессиональный; без канцелярита.  
• Каждый раздел снабдить 1-2 эмодзи (не превращать в «ёлку»).  
• Ключевые цифры выделяй **жирным**.  
• После каждого блока добавь строку _«Что это значит для инвестора?»_.  
• Используй маркеры «•» вместо * в списках, чтобы не конфликтовать с Markdown.  
• В конце дай мини-стратегию: «⚡️ Идея дня» — 2-3 предложения.  
• ≤ 450 слов. MarkdownV2: экранируй _ * [ ] ( ) ~ ` > # + - = | {{ }} . ! ' "

Структура:
1. Заголовок — жирный с датой и эмодзи 📈  
2. **Индексы** 📊 — S&P 500, DAX, Nikkei, Nasdaq fut + вывод  
3. **Акции-лидеры** 🚀 и аутсайдеры 📉 — по 2-3; вывод  
4. **Крипта** ₿ — BTC, ETH + топ-3 альткоина; вывод  
5. **Макро-новости** 📰 — 2-3 пункта + расшифровка влияния  
6. **Цитаты дня** 🗣 — до 3 цитат (Маск, Олтман, ФРС) + смысл  
7. **Число-факт** 🤔 — жирное число + контекст  
8. **⚡️ Идея дня** — чёткий actionable-вывод (пример: рост спроса на AI-чипы → смотрим на NVIDIA и поставщиков HBM-памяти)
"""

# ── helpers ─────────────────────────────────────────────────────────────────────
# экранируем всё, что Telegram MarkdownV2 расценивает как разметку
MD_V2_ESC = re.compile(r'([_*[\]()~`>#+\-=|{}.!\'"\\])')

def escape_md(text: str) -> str:
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
                max_tokens=700
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

def post_to_tg(text: str):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    for part in split_long(text):
        safe = escape_md(part)
        r = requests.post(url, json={
            "chat_id": CHANNEL_ID,
            "text": safe,
            "parse_mode": "MarkdownV2",
            "disable_web_page_preview": True
        }, timeout=10)
        if r.status_code != 200:
            log(f"Telegram error {r.status_code}: {r.text}")
        sleep(1)

# ── main ────────────────────────────────────────────────────────────────────────
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

