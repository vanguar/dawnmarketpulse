#!/usr/bin/env python3
import os
import sys
import requests
import openai
from datetime import datetime, timezone, date
from textwrap import wrap
from time import sleep

# ── ENV ─────────────────────────────────────────────────────────
openai.api_key = os.getenv("OPENAI_KEY")
TG_TOKEN = os.getenv("TG_TOKEN")
CHAT_ID = os.getenv("CHANNEL_ID")

MODEL = "gpt-4o-mini"
TIMEOUT = 60
GPT_TOKENS = 450  # ~1700-1900 символов, нейросеть должна стараться уложиться в это
TG_LIMIT_BYTES = 4096  # Лимит Telegram в байтах

# Уменьшаем значительно для тестирования, чтобы гарантированно не обрезалось
# Будем ориентироваться на байты, но textwrap работает с символами, поэтому нужен большой запас
# Примерно 2500 символов, чтобы с учетом многобайтовых символов и префикса не превысить лимит байт
TARGET_CHAR_LEN_FOR_CHUNK = 2500

# ── PROMPT ──────────────────────────────────────────────────────
PROMPT = """
🗓️ **Утренний обзор • {date}** ☀️

---

📊 **Ситуация на рынках:**

* Индексы (S&P 500, DAX, Nikkei, Nasdaq fut):
    * _Основные движения и показатели._
    * ➡️ _Что это значит для инвестора? Краткий анализ._

---

🚀 **Акции: Взлеты и Падения** 📉

* Лидеры роста (2-3 бумаги):
    * _Название компании (тикер): причина роста (новость, отчет, и т.д.)._
* Аутсайдеры (2-3 бумаги):
    * _Название компании (тикер): причина падения._
* ➡️ _Общий вывод по динамике акций._

---

₿ **Криптовалюты: Обзор** 💎

* Основные монеты (BTC, ETH):
    * _Динамика, ключевые уровни._
* Интересные альткоины (до 3):
    * _Название: краткая сводка, причина интереса._
* ➡️ _Вывод по крипторынку._

---

📰 **Главные макро-новости:**

* _(Заголовок 1): Краткое описание и потенциальное влияние._
* _(Заголовок 2): Краткое описание и потенциальное влияние._
* _(Заголовок 3): Краткое описание и потенциальное влияние._

---

🗣️ **Цитаты дня:**

* _"Цитата 1"_ - _Автор/Источник. (Краткий смысл или контекст)._
* _"Цитата 2"_ - _Автор/Источник. (Краткий смысл или контекст)._ (Если есть)

---

🤔 **Число / Факт дня:**

* _Интересный экономический или финансовый факт/число и его значение._

---

💡 **Идея дня / Actionable совет:**

* ⚡️ _Конкретный совет или идея на 1-2 предложения, что можно сделать сегодня/в ближайшее время._

---
‼️ **ВАЖНЕЙШЕЕ ТРЕБОВАНИЕ К ФОРМАТУ ОТВЕТА:**
1.  **ТОЛЬКО ОБЫЧНЫЙ ТЕКСТ.**
2.  **ЗАПРЕЩЕНО ИСПОЛЬЗОВАТЬ HTML, MARKDOWN или любые другие языки разметки.**
3.  **НЕ ИСПОЛЬЗУЙ ЗВЕЗДОЧКИ (`*`) или ПОДЧЕРКИВАНИЯ (`_`) для выделения текста (жирный, курсив) или для создания списков.**
4.  Если нужны списки, используй дефисы (`- `) или стандартные маркеры абзацев (например, `• `), но убедись, что вокруг них есть пробелы.
5.  Эмодзи активно приветствуются для наглядности и должны быть частью обычного текста.
6.  Общий объем ответа от тебя не должен превышать примерно 1600-1800 символов.
"""

TG_URL = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"

def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S %Z}] {msg}", flush=True)

def clean_text_from_potential_markdown(text: str) -> str:
    """Простая очистка от некоторых Markdown-подобных конструкций, если GPT их добавит."""
    # Убираем парные звездочки/подчеркивания, которые могут обозначать жирный/курсив
    # Это очень грубая замена и может затронуть легитимные символы, если они не являются разметкой.
    # text = text.replace("**", "").replace("__", "") # Возможно, это слишком агрессивно
    # text = text.replace("*", "").replace("_", "") # Еще агрессивнее
    
    # Более мягкий подход: если звездочка используется как маркер списка в начале строки
    # text = re.sub(r"^\*\s+", "- ", text, flags=re.MULTILINE) # Если бы использовали re
    
    # Пока что, учитывая строгий промпт, не будем делать агрессивную автозамену,
    # чтобы не испортить текст, если звездочки используются осмысленно (например, в тикерах).
    # Главная ставка на корректный промпт.
    return text

def gpt_report() -> str:
    try:
        resp = openai.ChatCompletion.create(
            model=MODEL,
            messages=[{"role": "user", "content": PROMPT.format(date=date.today().strftime("%d.%m.%Y"))}],
            timeout=TIMEOUT,
            temperature=0.4,
            max_tokens=GPT_TOKENS, # GPT_TOKENS определяет максимальное количество токенов в ответе *нейросети*
        )
        generated_text = resp.choices[0].message.content.strip()
        # cleaned_text = clean_text_from_potential_markdown(generated_text)
        log(f"GPT generated text length: {len(generated_text)} chars")
        return generated_text # Пока возвращаем без очистки, полагаясь на промпт
    except openai.error.OpenAIError as e:
        log(f"OpenAI API Error: {e}")
        raise
    except Exception as e:
        log(f"Error in gpt_report: {e}")
        raise

def chunk_text(text: str, target_char_len: int = TARGET_CHAR_LEN_FOR_CHUNK):
    # Запас для префикса (например, "(10/10)\n" ~ 10 символов) и непредвиденных случаев
    # textwrap работает с количеством символов, не байт.
    wrap_width = target_char_len - 60 # Дополнительный запас от целевой длины символов
    
    log(f"Original text length for chunking: {len(text)} chars, {len(text.encode('utf-8'))} bytes.")
    log(f"Chunking with wrap_width: {wrap_width} chars.")

    parts = wrap(text, width=wrap_width,
                 break_long_words=False, # Стараемся не рвать слова
                 replace_whitespace=False, # Сохраняем переносы строк от GPT
                 drop_whitespace=True, # Удаляем лишние пробелы по краям частей
                 break_on_hyphens=False)
    
    total_parts = len(parts)
    if total_parts == 0 and text.strip(): # Если текст был, но wrap ничего не вернул (очень короткий)
        parts = [text.strip()]
        total_parts = 1
    elif total_parts == 0: # Если текст был пустой
        return [""]

    chunked_messages = []
    for i, p_text in enumerate(parts):
        current_part_text = p_text.strip()
        if not current_part_text: # Пропускаем полностью пустые части
            continue

        if total_parts > 1:
            message_with_prefix = f"({i+1}/{total_parts})\n{current_part_text}"
        else:
            message_with_prefix = current_part_text
        chunked_messages.append(message_with_prefix)
        
    return chunked_messages

def send(part_text: str):
    if not part_text:
        log("Attempted to send an empty part. Skipping.")
        return

    char_len = len(part_text)
    byte_len = len(part_text.encode('utf-8'))
    log(f"Sending part: {char_len} chars, {byte_len} bytes. (TG Limit: {TG_LIMIT_BYTES} bytes)")

    if byte_len > TG_LIMIT_BYTES:
        log(f"ERROR: Part is too long in bytes! {byte_len} > {TG_LIMIT_BYTES}. Truncating (this is a bugfix attempt, ideally chunking should prevent this).")
        # Это аварийная обрезка по байтам, если логика chunk_text не справилась.
        # Она может обрезать не по символу, а по середине многобайтового символа, что плохо.
        part_text = part_text.encode('utf-8')[:TG_LIMIT_BYTES].decode('utf-8', 'ignore')
        log(f"Post-truncation: {len(part_text)} chars, {len(part_text.encode('utf-8'))} bytes.")


    json_payload = {
        "chat_id": CHAT_ID,
        "text": part_text,
        "disable_web_page_preview": True
        # "parse_mode" НЕ УКАЗЫВАЕМ, чтобы был plain text
    }
    try:
        r = requests.post(TG_URL, json=json_payload, timeout=20) # Увеличил таймаут на всякий случай
        r.raise_for_status()
        log(f"Part sent successfully to {CHAT_ID}.")
    except requests.exceptions.HTTPError as e:
        log(f"TG HTTP Error {r.status_code} for {CHAT_ID}: {r.text}. Error: {e}")
        # Если ошибка 400 "Bad Request: message is too long", то проблема с длиной осталась
        if r.status_code == 400 and "message is too long" in r.text.lower():
            log("CRITICAL: TELEGRAM REPORTS MESSAGE IS TOO LONG DESPITE CHUNKING. Review chunking logic and byte counts.")
    except requests.exceptions.RequestException as e:
        log(f"TG Request Error for {CHAT_ID}: {e}")
    except Exception as e:
        log(f"Generic error in send function for {CHAT_ID}: {e}")

def main():
    log("Script started. Attempting to generate and send report...")
    try:
        report_text = gpt_report()
        if not report_text or report_text.isspace():
            log("GPT returned an empty or whitespace-only report. Exiting.")
            return

        segments = chunk_text(report_text)
        if not segments or not any(s.strip() for s in segments):
            log("Chunking resulted in no valid segments. Exiting.")
            return

        log(f"Report chunked into {len(segments)} segment(s).")

        for i, seg_text in enumerate(segments):
            log(f"Processing segment {i+1}/{len(segments)}...")
            send(seg_text)
            if i < len(segments) - 1:
                sleep(2) # Увеличил паузу
        log("All segments processed. Posted OK.")
    except openai.error.OpenAIError as e:
        log(f"Fatal OpenAI API Error: {e}")
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        log(f"Fatal Telegram API Request Error: {e}")
        sys.exit(1)
    except Exception as e:
        log(f"Fatal error in main execution: {e}")
        import traceback
        log(f"Traceback: {traceback.format_exc()}")
        sys.exit(1)

if __name__ == "__main__":
    main()
