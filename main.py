#!/usr/bin/env python3
import os
import sys
import requests
import openai
from datetime import datetime, timezone, date
from textwrap import wrap
from time import sleep
import traceback

# Загружаем ключи и настройки из переменных окружения
openai.api_key = os.getenv("OPENAI_KEY")
TG_TOKEN       = os.getenv("TG_TOKEN")
CHANNEL_ID     = os.getenv("CHANNEL_ID")

# Настройки модели и Telegram
MODEL       = "gpt-4o-mini"
TIMEOUT     = 60
TG_LIMIT    = 4096      # Максимум символов в одном сообщении Telegram
GPT_TOKENS  = 400       # Примерно 1600–1800 символов

# Промпт, который отправляется в GPT каждый день
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
→ Вывод.

Макро-новости 📰
• 3 главных заголовка + влияние

Цитаты дня 🗣
• до 2 цитат + смысл

Число-факт 🤔

⚡️ Идея дня – 2 предложения actionable-совета.

‼️ Только обычный текст, без HTML. Максимум 1 600 символов.
"""

# Функция логирования — пишет в консоль и дублирует сообщение в Telegram
def log(msg):
    timestamp = f"[{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC]"
    print(f"{timestamp} {msg}", flush=True)
    if TG_TOKEN and CHANNEL_ID:
        try:
            requests.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": CHANNEL_ID, "text": f"🛠 {msg}"},
                timeout=5
            )
        except Exception as e:
            print(f"{timestamp} ❗ Ошибка логирования в Телеграм: {e}", flush=True)

# Генерация текста GPT
def gpt_report():
    r = openai.ChatCompletion.create(
        model=MODEL,
        messages=[{"role": "user", "content": PROMPT.format(date=date.today())}],
        timeout=TIMEOUT,
        temperature=0.4,
        max_tokens=GPT_TOKENS,
    )
    return r.choices[0].message.content.strip()

# Разбиваем длинный текст на части для Telegram
def chunk(text, limit=TG_LIMIT):
    parts = wrap(text, width=limit-20, break_long_words=False, break_on_hyphens=False)
    total = len(parts)
    return [f"({i+1}/{total})\n{p}" if total > 1 else p for i, p in enumerate(parts)]

# Отправка текста в Telegram
def send(text):
    for part in chunk(text):
        r = requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": CHANNEL_ID, "text": part, "disable_web_page_preview": True},
            timeout=10
        )
        if r.status_code != 200:
            log(f"❗ Ошибка отправки в TG: {r.status_code}: {r.text}")
        sleep(1)  # небольшая пауза между частями

# Главная точка запуска
def main():
    log("Скрипт Railway по расписанию запущен.")
    try:
        report = gpt_report()
        send(report)
        log("✅ Пост успешно опубликован.")
    except Exception as e:
        log(f"❌ Ошибка выполнения: {e}")
        log(traceback.format_exc())
        sys.exit(1)

# Запуск только при запуске скрипта напрямую
if __name__ == "__main__":
    main()


