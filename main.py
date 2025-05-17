#!/usr/bin/env python3
import nltk
nltk.download('punkt')
nltk.download('wordnet')
nltk.download('averaged_perceptron_tagger')

import os
import sys
import requests
import openai
from datetime import datetime, timezone, date
from time import sleep
import traceback
import re

# Подключаем внешний модуль
from market_reader import get_market_data_text, get_crypto_data
# from tweets_reader import get_tweet_digest   # Временно отключено
from news_reader import get_news_block
from analyzer import keyword_alert, store_and_compare
from report_utils import analyze_sentiment  # generate_pdf удалён

# Загружаем переменные окружения
openai.api_key = os.getenv("OPENAI_KEY")
TG_TOKEN = os.getenv("TG_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

# Настройки
MODEL       = "gpt-4o-mini"
TIMEOUT     = 60
TG_LIMIT    = 4096
GPT_TOKENS  = 400

# Хвост промпта после данных
GPT_CONTINUATION = """
Акции-лидеры 🚀 / Аутсайдеры 📉
- по 2–3 бумаги + причина
→ Вывод.

Макро-новости 📰
- 3 главных заголовка + влияние

Цитаты дня 🗣
- до 2 цитат + смысл

Число-факт 🤔

⚡️ Идея дня – 2 предложения actionable-совета.

‼️ Только обычный текст, без HTML.
‼️ Структурируй текст с ДВОЙНЫМИ переносами строк между абзацами.
‼️ Используй эмодзи перед заголовками разделов.
"""

def log(msg):
    timestamp = f"[{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC]"
    print(f"{timestamp} {msg}", flush=True)
    if TG_TOKEN and CHANNEL_ID:
        try:
            requests.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": CHANNEL_ID, "text": f"🛠 {timestamp} - {msg}"},
                timeout=5
            )
        except Exception as e:
            print(f"{timestamp} ❗ Ошибка логирования в Телеграм: {e}", flush=True)

def gpt_report():
    dynamic_data = (
        get_market_data_text() + "\n\n" +
        get_crypto_data() + "\n\n" +
        get_news_block() + "\n\n" +
        GPT_CONTINUATION
    )
    r = openai.ChatCompletion.create(
        model=MODEL,
        messages=[{"role": "user", "content": dynamic_data}],
        timeout=TIMEOUT,
        temperature=0.4,
        max_tokens=GPT_TOKENS,
    )
    return r.choices[0].message.content.strip()

def prepare_text(text):
    for marker in ["📊", "🚀", "📉", "₿", "📰", "🗣", "🤔", "⚡️"]:
        text = re.sub(f"({marker}[^\n]+)\n", f"\1\n\n", text)
    text = re.sub(r"\n→", "\n\n→", text)
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text

def chunk(text, limit=TG_LIMIT):
    paragraphs = text.split("\n\n")
    chunks = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 2 <= limit:
            current += (para + "\n\n")
        else:
            chunks.append(current.strip())
            current = para + "\n\n"
    if current:
        chunks.append(current.strip())
    return chunks

def send(text):
    text = prepare_text(text)
    for part in chunk(text):
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": CHANNEL_ID, "text": part, "disable_web_page_preview": True},
                timeout=10
            )
            if r.status_code != 200:
                log(f"❗ Ошибка отправки в TG: {r.status_code}: {r.text}")
            else:
                log(f"✅ Часть сообщения успешно отправлена ({len(part)} символов)")
        except Exception as e:
            log(f"❗ Ошибка при отправке: {e}")
        sleep(1)

def main():
    log("🚀 Railway запустил скрипт по расписанию.")
    try:
        report = gpt_report()
        log(f"📝 Сгенерирован отчёт ({len(report)} символов)")
        send(report)
        send(keyword_alert(report))
        send(store_and_compare(report))
        send(analyze_sentiment(report))
        log("✅ Отчёт успешно отправлен в Telegram.")
    except Exception as e:
        log(f"❌ Ошибка выполнения: {e}")
        log(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main()
