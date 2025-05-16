#!/usr/bin/env python3
"""
Daily market report → Telegram-канал.
Запускается по крону на Railway (07:05 UTC ≈ 09:05 Europe/Kyiv).

ENV:
  OPENAI_KEY  – ключ OpenAI
  TG_TOKEN    – токен бота
  CHANNEL_ID  – @username канала или -100… ID
  TZ          – Europe/Berlin (устанавливается в Railway Variables)
"""

import os, sys, html, requests, openai
from datetime import datetime, timezone, date
from time import sleep

# ───────────  ENV & базовые настройки  ────────────────────────────────────────
openai.api_key = os.getenv("OPENAI_KEY")
TG_TOKEN       = os.getenv("TG_TOKEN")
CHANNEL_ID     = os.getenv("CHANNEL_ID")

MODEL          = "gpt-4o-mini"       # можно 'gpt-4o'
RETRIES        = 3
TIMEOUT        = 60
MAX_TG_LEN     = 4096                # лимит Telegram

# ───────────  PROMPT  ─────────────────────────────────────────────────────────
USER_PROMPT = """
<b>📈 Утренний обзор • {date}</b>

<b>Индексы 📊</b>
• S&P 500, DAX, Nikkei, Nasdaq fut  
<i>Что это значит для инвестора?</i>

<b>Акции-лидеры 🚀</b> и <b>Аутсайдеры 📉</b>
• по 2–3 бумаги + вывод

<b>Крипта ₿</b>
• BTC, ETH + 3 перспективных альткоина + вывод

<b>Макро-новости 📰</b>
• три пункта + расшифровка влияния

<b>Цитаты дня 🗣</b>
• до 3 цитат + краткая интерпретация

<b>Число-факт 🤔</b>

<b>⚡️ Идея дня</b> — 2–3 предложения actionable-совета

Требования:
• Пиши ТОЛЬКО в HTML-разметке (<b>,<i>,<u>,<s>,<code>,<a>).  
• Списки начинай маркером «• ».  
• Тон дружелюбный, но профессиональный; ≤ 450 слов.
"""

# ───────────  helpers  ────────────────────────────────────────────────────────
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
                max_tokens=700,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            log(f"OpenAI error: {e}")
            if n == RETRIES:
                raise
            sleep(2 ** n)

def safe_html(text: str) -> str:
    """Экранируем &,<,> и сохраняем разрывы строк → <br>."""
    return html.escape(text, quote=False).replace("\n", "<br>")

def split_long(text: str):
    """Делим по АБЗАЦАМ, чтобы не рвать HTML-теги."""
    if len(text) <= MAX_TG_LEN:
        return [text]
    parts, chunk, length = [], [], 0
    for para in text.split("\n\n"):
        para += "\n\n"
        if length + len(para) > MAX_TG_LEN:
            parts.append(''.join(chunk))
            chunk, length = [], 0
        chunk.append(para)
        length += len(para)
    if chunk:
        parts.append(''.join(chunk))
    return parts

def post_to_tg(text: str):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    for part in split_long(text):
        payload = {
            "chat_id": CHANNEL_ID,
            "text": safe_html(part),
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            log(f"Telegram error {r.status_code}: {r.text}")
        sleep(1)

# ───────────  main  ───────────────────────────────────────────────────────────
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



