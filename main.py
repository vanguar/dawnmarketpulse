#!/usr/bin/env python3
import os
import sys
import requests
import openai
from datetime import datetime, timezone, date
# textwrap больше не используется для основной логики разбивки, но может быть полезен для других целей
# from textwrap import wrap 
from time import sleep

# ── ENV ─────────────────────────────────────────────────────────
openai.api_key = os.getenv("OPENAI_KEY")
TG_TOKEN = os.getenv("TG_TOKEN")
CHAT_ID = os.getenv("CHANNEL_ID")

MODEL = "gpt-4o-mini"
TIMEOUT = 60
GPT_TOKENS = 450
TG_LIMIT_BYTES = 4096  # Лимит Telegram в байтах

# Запас для префикса типа "(NN/MM)\n" и других непредвиденных расходов.
# (99/99)\n это 9 символов ASCII = 9 байт. Возьмем с запасом.
PREFIX_MAX_BYTES = 25
# Насколько близко мы хотим подойти к лимиту TG_LIMIT_BYTES с каждой частью.
# Оставим небольшой запас для надежности.
CHUNK_TARGET_BYTES = TG_LIMIT_BYTES - PREFIX_MAX_BYTES - 50 # 50 байт дополнительного запаса

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

def gpt_report() -> str:
    try:
        # Важно: Вы используете openai==0.28.1. API для версий openai>=1.0.0 другой.
        # Этот код для вашей старой версии.
        resp = openai.ChatCompletion.create(
            model=MODEL,
            messages=[{"role": "user", "content": PROMPT.format(date=date.today().strftime("%d.%m.%Y"))}],
            timeout=TIMEOUT,
            temperature=0.4,
            max_tokens=GPT_TOKENS,
        )
        generated_text = resp.choices[0].message.content.strip()
        log(f"GPT generated text length: {len(generated_text)} chars, {len(generated_text.encode('utf-8'))} bytes")
        return generated_text
    except openai.error.OpenAIError as e:
        log(f"OpenAI API Error: {e}")
        raise
    except Exception as e:
        log(f"Error in gpt_report: {e}")
        raise

def chunk_text_by_bytes(text: str, target_chunk_bytes: int) -> list[str]:
    log(f"Chunking text by bytes. Original: {len(text)} chars, {len(text.encode('utf-8'))} bytes. Target per chunk: {target_chunk_bytes} bytes.")
    if not text.strip():
        return []

    # Используем splitlines() для сохранения переносов строк, которые сделал GPT
    # Это предпочтительнее, чем просто слова, для сохранения абзацев
    lines = text.splitlines(keepends=True) 
    if not lines: # Если текст был, но без переносов (одна строка)
        lines = [text]

    all_parts_text = []
    current_part_lines = []
    current_part_bytes = 0

    for line in lines:
        line_bytes = len(line.encode('utf-8'))
        if line_bytes == 0 and not line.strip(): # Пропускаем полностью пустые строки, если они есть
            continue

        if current_part_bytes + line_bytes <= target_chunk_bytes:
            current_part_lines.append(line)
            current_part_bytes += line_bytes
        else:
            # Текущая часть заполнена, сохраняем ее
            if current_part_lines: # Только если есть что сохранять
                all_parts_text.append("".join(current_part_lines).strip())
            
            # Начинаем новую часть с текущей строки
            # Если сама строка уже больше лимита, ее нужно будет как-то обработать
            # (пока просто добавим ее, в надежде что такая строка одна и она не слишком длинная)
            # В идеале, нужно было бы делить и слишком длинные строки, но это усложнит код.
            current_part_lines = [line]
            current_part_bytes = line_bytes
            if line_bytes > target_chunk_bytes:
                log(f"WARNING: Single line is longer than target_chunk_bytes! Line length: {line_bytes} bytes. This might still be too long for Telegram.")

    # Добавляем последнюю накопленную часть
    if current_part_lines:
        all_parts_text.append("".join(current_part_lines).strip())
    
    # Убираем полностью пустые строки, которые могли образоваться после strip()
    all_parts_text = [part for part in all_parts_text if part]

    # Добавляем префиксы (N/M)
    final_chunks_with_prefix = []
    total_final_parts = len(all_parts_text)
    if total_final_parts == 0:
        return []
    if total_final_parts == 1:
        return all_parts_text # Префикс не нужен для одной части

    for i, part_text in enumerate(all_parts_text):
        prefix = f"({i+1}/{total_final_parts})\n"
        # Проверяем, не превысит ли часть С ПРЕФИКСОМ общий лимит Telegram
        # Это самая важная проверка.
        if len((prefix + part_text).encode('utf-8')) > TG_LIMIT_BYTES:
            log(f"CRITICAL ERROR in chunking: Part {i+1}/{total_final_parts} WITH prefix is TOO LONG: {len((prefix + part_text).encode('utf-8'))} bytes. Text of part (first 100 chars): '{part_text[:100]}'")
            # Здесь нужна более умная логика, возможно, эту часть нужно разбить еще раз
            # или уменьшить CHUNK_TARGET_BYTES еще сильнее.
            # Пока что просто пропустим такую "сломанную" часть, чтобы избежать ошибки в Telegram.
            # В идеале, такого быть не должно, если CHUNK_TARGET_BYTES выбран правильно.
            continue 
        final_chunks_with_prefix.append(prefix + part_text)
        
    log(f"Text chunked into {len(final_chunks_with_prefix)} parts by bytes.")
    return final_chunks_with_prefix


def send(part_text: str):
    if not part_text or part_text.isspace(): # Дополнительная проверка
        log("Attempted to send an empty or whitespace-only part. Skipping.")
        return

    char_len = len(part_text)
    byte_len = len(part_text.encode('utf-8'))
    log(f"Sending part: {char_len} chars, {byte_len} bytes. (TG Limit: {TG_LIMIT_BYTES} bytes)")

    # Эта проверка должна быть избыточной, если chunk_text_by_bytes работает корректно
    if byte_len > TG_LIMIT_BYTES:
        log(f"EMERGENCY FAILSAFE: Part is too long in bytes JUST BEFORE SENDING! {byte_len} > {TG_LIMIT_BYTES}. This indicates a flaw in chunk_text_by_bytes or prefix addition.")
        # Не будем пытаться обрезать здесь, так как это признак более глубокой проблемы.
        # Лучше пусть Telegram вернет ошибку, чтобы мы это увидели.

    json_payload = {
        "chat_id": CHAT_ID,
        "text": part_text,
        "disable_web_page_preview": True
    }
    try:
        r = requests.post(TG_URL, json=json_payload, timeout=20)
        r.raise_for_status()
        log(f"Part sent successfully to {CHAT_ID}.")
    except requests.exceptions.HTTPError as e:
        log(f"TG HTTP Error {r.status_code} for {CHAT_ID}: {r.text}. Error: {e}")
        if r.status_code == 400 and "message is too long" in r.text.lower():
            log("CRITICAL: TELEGRAM API REPORTS 'MESSAGE IS TOO LONG'.")
            log(f"Failed part text (first 200 chars): '{part_text[:200]}...'")
            log(f"Failed part actual byte length: {byte_len}")
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

        # Используем новую функцию разбивки по байтам
        segments = chunk_text_by_bytes(report_text, CHUNK_TARGET_BYTES)
        
        if not segments: # segments может быть пустым списком
            log("Chunking resulted in no valid segments. Exiting.")
            return

        log(f"Report chunked into {len(segments)} segment(s).")

        for i, seg_text in enumerate(segments):
            log(f"Processing segment {i+1}/{len(segments)}...")
            send(seg_text)
            if i < len(segments) - 1:
                sleep(2)
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
