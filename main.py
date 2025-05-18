#!/usr/bin/env python3
import nltk
nltk.download('punkt', quiet=True)
nltk.download('wordnet', quiet=True)
nltk.download('averaged_perceptron_tagger', quiet=True)

import os
import sys
import requests
import openai
from datetime import datetime, timezone, date
from time import sleep
import traceback
import re

from market_reader import get_market_data_text, get_crypto_data
from news_reader import get_news_block
from analyzer import keyword_alert, store_and_compare
from report_utils import analyze_sentiment

# --- Конфигурация ---
openai.api_key = os.getenv("OPENAI_KEY")
TG_TOKEN = os.getenv("TG_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

MODEL = "gpt-4o-mini"
TIMEOUT = 60  # Таймаут для API запросов (например, OpenAI)
TG_LIMIT_BYTES = 3800  # Байтовый лимит для ТЕКСТА одного сообщения (без префикса)
GPT_TOKENS = 400 # Максимальное количество токенов для ответа от GPT

GPT_CONTINUATION = """Акции-лидеры 🚀 / Аутсайдеры 📉
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
‼️ Используй эмодзи перед заголовками разделов."""

# --- Вспомогательные функции ---

def log(msg):
    timestamp = f"[{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC]"
    print(f"{timestamp} {msg}", flush=True)

def safe_call(func, retries=3, delay=5, label="❗ Ошибка"):
    for i in range(retries):
        try:
            return func()
        except Exception as e:
            log(f"{label}: попытка {i + 1}/{retries} не удалась: {e}")
            if i < retries - 1:
                sleep(delay)
    log(f"{label}: все {retries} попытки провалены.")
    return None

# --- Сбор данных и генерация отчета ---

def gpt_report():
    today = date.today().strftime("%d.%m.%Y")
    header = f"📅 Актуальные рыночные новости на {today}"
    
    # Собираем данные от всех модулей
    market_data_text = get_market_data_text()
    crypto_data_text = get_crypto_data(extended=True)
    news_block_text = get_news_block()

    dynamic_data = (
        f"{header}\n\n"
        f"{market_data_text}\n\n"
        f"{crypto_data_text}\n\n"
        f"{news_block_text}\n\n" # get_news_block УЖЕ содержит свой заголовок и GPT_CONTINUATION для новостей
        f"{GPT_CONTINUATION}" # Это общий GPT_CONTINUATION для других секций, если они будут
    )
    
    log(f"ℹ️ Данные для GPT (первые 300 симв): {dynamic_data[:300]}...")
    log(f"ℹ️ Общая длина данных для GPT: {len(dynamic_data)} символов")

    response = safe_call(
        lambda: openai.ChatCompletion.create(
            model=MODEL,
            messages=[{"role": "user", "content": dynamic_data}],
            timeout=TIMEOUT,
            temperature=0.4,
            max_tokens=GPT_TOKENS,
        ),
        label="❗ Ошибка OpenAI"
    )
    if not response:
        raise RuntimeError("OpenAI не ответил после нескольких попыток.")
    
    generated_text = response.choices[0].message.content.strip()
    log(f"📝 GPT сгенерировал ответ ({len(generated_text)} символов)")
    return generated_text

# --- Обработка и отправка текста в Telegram ---

def prepare_text(text):
    # Убедимся, что после заголовков с эмодзи всегда два переноса строки
    for marker in ["📊", "🚀", "📉", "₿", "📰", "🗣", "🤔", "⚡️", "🔍", "📈", "🧠"]: # Добавил маркеры из main
        text = re.sub(f"({marker}[^\n]+)\n(?!\n)", r"\1\n\n", text)
    # Убедимся, что после стрелочки "→" всегда два переноса строки
    text = re.sub(r"\n→", "\n\n→", text)
    # Убираем тройные и более переносы строк
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text.strip()

def force_split_long_string(long_str, limit_b):
    """Безопасно режет длинную строку на части, не превышающие limit_b байт."""
    sub_chunks = []
    if not long_str:
        return sub_chunks
    
    encoded_str = long_str.encode('utf-8')
    start_idx = 0
    while start_idx < len(encoded_str):
        end_idx = min(start_idx + limit_b, len(encoded_str))
        current_byte_slice = encoded_str[start_idx:end_idx]
        
        # Пытаемся декодировать, отступая по байту назад при ошибке
        while True:
            try:
                decoded_chunk = current_byte_slice.decode('utf-8')
                sub_chunks.append(decoded_chunk)
                start_idx += len(current_byte_slice) # Переходим к следующей позиции
                break 
            except UnicodeDecodeError:
                if len(current_byte_slice) > 1:
                    current_byte_slice = current_byte_slice[:-1] # Уменьшаем на 1 байт
                else:
                    # Не удалось декодировать даже 1 байт. Это крайний случай.
                    # Пропускаем этот байт, чтобы избежать бесконечного цикла.
                    log(f"⚠️ Пропущен проблемный байт при принудительной нарезке: {encoded_str[start_idx:start_idx+1]!r}")
                    start_idx += 1
                    break # Выход из внутреннего while, переход к следующей итерации внешнего
    return sub_chunks

def smart_chunk(text_to_split_paragraphs, outer_limit_bytes):
    """Разбивает текст на чанки с учетом байтового лимита, стараясь сохранять абзацы."""
    paragraphs = text_to_split_paragraphs.split("\n\n")
    final_chunks = []
    current_chunk_text_parts = []
    current_chunk_accumulated_bytes = 0

    for para_idx, para_str in enumerate(paragraphs):
        if not para_str.strip(): # Пропускаем пустые абзацы
            continue

        para_bytes = para_str.encode('utf-8')
        # Байты для разделителя "\n\n" (2 байта), если текущий чанк не пуст
        separator_bytes_len = 2 if current_chunk_text_parts else 0 

        if current_chunk_accumulated_bytes + separator_bytes_len + len(para_bytes) <= outer_limit_bytes:
            # Абзац помещается в текущий чанк
            if current_chunk_text_parts: # Добавляем разделитель, если это не первый абзац в чанке
                current_chunk_text_parts.append("\n\n")
            current_chunk_text_parts.append(para_str)
            current_chunk_accumulated_bytes += separator_bytes_len + len(para_bytes)
        else:
            # Абзац не помещается. Завершаем текущий чанк, если он не пуст.
            if current_chunk_text_parts:
                final_chunks.append("".join(current_chunk_text_parts))
            # Сбрасываем текущий чанк
            current_chunk_text_parts = []
            current_chunk_accumulated_bytes = 0

            # Теперь обрабатываем 'para_str', который не поместился
            if len(para_bytes) > outer_limit_bytes:
                # Сам абзац длиннее лимита, его нужно принудительно резать
                log(f"ℹ️ Абзац #{para_idx} слишком длинный ({len(para_bytes)} байт), будет разрезан.")
                split_long_paragraph_parts = force_split_long_string(para_str, outer_limit_bytes)
                final_chunks.extend(split_long_paragraph_parts) # Каждый кусок - новый чанк
            else:
                # Абзац не длиннее лимита, но не влез в предыдущий чанк. Начинаем им новый чанк.
                current_chunk_text_parts.append(para_str)
                current_chunk_accumulated_bytes = len(para_bytes)
                
    # Добавляем последний собранный чанк, если он не пуст
    if current_chunk_text_parts:
        final_chunks.append("".join(current_chunk_text_parts))

    return [chunk for chunk in final_chunks if chunk.strip()] # Убираем полностью пустые чанки

def send(text_to_send, add_numeration=False):
    prepared_text = prepare_text(text_to_send)
    
    # Запас байт под префикс "Часть XX/YY:\n\n"
    # "Часть 10/10:\n\n" ~ 15 символов. В UTF-8 это может быть до 15*4=60 байт, но обычно меньше.
    # Возьмем консервативный запас.
    prefix_allowance_bytes = 40 
    
    text_part_limit_bytes = TG_LIMIT_BYTES
    if add_numeration:
        text_part_limit_bytes = TG_LIMIT_BYTES - prefix_allowance_bytes
    
    parts = smart_chunk(prepared_text, text_part_limit_bytes)
    total_parts = len(parts)

    if not parts:
        log("ℹ️ Нет частей для отправки (текст пуст или состоит только из пробелов).")
        return

    for idx, part_content in enumerate(parts, 1):
        final_text_to_send = part_content
        log_message_prefix = "" # Для логов, чтобы было понятно, какая часть

        if add_numeration and total_parts > 0: # Нумерация только если указано и есть части
            prefix_str = f"Часть {idx}/{total_parts}:\n\n"
            final_text_to_send = prefix_str + part_content
            log_message_prefix = f"Часть {idx}/{total_parts} "
            
            # Проверка, не превысили ли мы АБСОЛЮТНЫЙ лимит Telegram с префиксом
            final_text_bytes = len(final_text_to_send.encode('utf-8'))
            if final_text_bytes > 4096:
                log(f"📛 ВНИМАНИЕ! {log_message_prefix}С ПРЕФИКСОМ СЛИШКОМ ДЛИННАЯ ({final_text_bytes} байт > 4096). Telegram ОБРЕЖЕТ ЭТУ ЧАСТЬ!")
                # Можно добавить логику дополнительной обрезки здесь, но это усложнит.
                # Пока что просто предупреждаем и отправляем.

        def send_telegram_request():
            return requests.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": CHANNEL_ID, "text": final_text_to_send, "disable_web_page_preview": True},
                timeout=10 # Таймаут на один запрос к Telegram
            )

        response = safe_call(send_telegram_request, label=f"❗ Ошибка отправки {log_message_prefix}в TG")
        
        if response and response.status_code == 200:
            log(f"✅ {log_message_prefix}успешно отправлена ({len(final_text_to_send.encode('utf-8'))} байт, {len(final_text_to_send)} символов)")
        elif response:
            log(f"❗ Ошибка от Telegram для {log_message_prefix.strip()}: {response.status_code} - {response.text}")
            log(f"   Текст проблемной части (первые 100 символов): {final_text_to_send[:100].replace(chr(10), ' ')}")
        else:
            log(f"❗ Не удалось отправить {log_message_prefix.strip()} (нет ответа от сервера Telegram).")
            log(f"   Текст проблемной части (первые 100 символов): {final_text_to_send[:100].replace(chr(10), ' ')}")

        if total_parts > 1 and idx < total_parts: # Пауза между отправкой частей
            sleep(1.5) # Немного увеличил паузу

# --- Основная логика скрипта ---

def main():
    log("🚀 Скрипт запущен.") # Изменил сообщение для ясности
    try:
        # 1. Генерируем основной текстовый отчет от GPT
        main_report_text = gpt_report()
        
        # 2. Собираем все компоненты отчета
        # Важно, чтобы каждая часть из keyword_alert, store_and_compare, analyze_sentiment
        # уже содержала свои заголовки, если они нужны.
        
        report_components = [
            "📊 Рыночный отчёт",
            main_report_text.strip(), # Текст от GPT
            
            keyword_alert(main_report_text).strip(), # Эта функция уже должна возвращать заголовок типа "🔍 Ключевые слова"
            
            store_and_compare(main_report_text).strip(), # Эта функция уже должна возвращать заголовок типа "📈 Сравнение с вчера"
            
            analyze_sentiment(main_report_text).strip() # Эта функция уже должна возвращать заголовок типа "🧠 Анализ тональности"
        ]
        
        # Объединяем все компоненты в одну большую строку с двойными переносами
        full_report_string = "\n\n".join(filter(None, report_components)) # filter(None, ...) уберет пустые строки, если какая-то функция вернула None или ""

        # 3. Отправляем собранный отчет в Telegram
        if full_report_string:
            send(full_report_string, add_numeration=True)
            log("✅ Весь отчёт обработан и отправлен.")
        else:
            log("ℹ️ Итоговый отчет пуст, отправка не требуется.")

    except RuntimeError as e: # Ошибка от OpenAI
        log(f"❌ Критическая ошибка OpenAI: {e}")
        # Можно отправить уведомление об ошибке в Telegram, если это необходимо
        # send(f"🔥 Ошибка генерации отчета: проблема с OpenAI. {e}", add_numeration=False)
        sys.exit(1) # Выход с ошибкой, чтобы Railway мог это зафиксировать
    except requests.exceptions.RequestException as e:
        log(f"❌ Критическая сетевая ошибка: {e}")
        log(traceback.format_exc())
        # send(f"🔥 Сетевая ошибка при работе скрипта. {e}", add_numeration=False)
        sys.exit(1)
    except Exception as e:
        log(f"❌ Непредвиденная глобальная ошибка: {e}")
        log(traceback.format_exc())
        # send(f"🔥 Непредвиденная ошибка в работе скрипта. {e}", add_numeration=False)
        sys.exit(1)

if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()


