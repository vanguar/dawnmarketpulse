#!/usr/bin/env python3
import nltk
# Используем quiet=True, чтобы не было лишних сообщений в логах при каждом запуске
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

# Предполагается, что эти модули находятся в том же каталоге или доступны через PYTHONPATH
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
# Устанавливаем байтовый лимит для ТЕКСТА ОДНОГО сообщения (без префикса "Часть X/Y")
# Это значение можно будет уменьшать, если обрезка продолжится.
TG_LIMIT_BYTES = 3700 # Попробуем уменьшить еще немного для большего запаса
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
        except requests.exceptions.Timeout:
            log(f"{label}: попытка {i + 1}/{retries} не удалась - Таймаут ({TIMEOUT}с)")
            if i < retries - 1:
                sleep(delay)
        except requests.exceptions.RequestException as e: # Более общая ошибка сети
            log(f"{label}: попытка {i + 1}/{retries} не удалась - Ошибка сети: {e}")
            if i < retries - 1:
                sleep(delay)
        except Exception as e:
            log(f"{label}: попытка {i + 1}/{retries} не удалась - Общая ошибка: {e}")
            log(traceback.format_exc()) # Логируем полный traceback для неожиданных ошибок
            if i < retries - 1:
                sleep(delay)
    log(f"{label}: все {retries} попытки провалены.")
    return None

# --- Сбор данных и генерация отчета ---

def gpt_report():
    today = date.today().strftime("%d.%m.%Y")
    header = f"📅 Актуальные рыночные новости на {today}"
    
    market_data_text = get_market_data_text()
    crypto_data_text = get_crypto_data(extended=True)
    news_block_text = get_news_block() # get_news_block уже включает заголовок и промпт для GPT

    dynamic_data = (
        f"{header}\n\n"
        f"{market_data_text}\n\n"
        f"{crypto_data_text}\n\n"
        f"{news_block_text}\n\n" 
        f"{GPT_CONTINUATION}" 
    )
    
    log(f"ℹ️ Данные для GPT (длина): {len(dynamic_data)} символов. Первые 200: {dynamic_data[:200]}...")

    response = safe_call(
        lambda: openai.ChatCompletion.create(
            model=MODEL,
            messages=[{"role": "user", "content": dynamic_data}],
            timeout=TIMEOUT, # Таймаут для запроса к OpenAI
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

def prepare_text(text_to_prepare):
    if not isinstance(text_to_prepare, str): # Добавим проверку типа
        log(f"⚠️ prepare_text получил не строку: {type(text_to_prepare)}. Возвращаю как есть.")
        return str(text_to_prepare) # Пытаемся преобразовать в строку на всякий случай

    for marker in ["📊", "🚀", "📉", "₿", "📰", "🗣", "🤔", "⚡️", "🔍", "📈", "🧠"]:
        text_to_prepare = re.sub(f"({marker}[^\n]*)\n(?!\n)", r"\1\n\n", text_to_prepare)
    
    text_to_prepare = re.sub(r"(\n→[^\n]*)\n(?!\n)", r"\1\n\n", text_to_prepare) 
    text_to_prepare = re.sub(r"(\n→)$", r"\1\n", text_to_prepare) 

    while "\n\n\n" in text_to_prepare:
        text_to_prepare = text_to_prepare.replace("\n\n\n", "\n\n")
    return text_to_prepare.strip()


def force_split_long_string(long_str, limit_b):
    sub_chunks = []
    if not long_str: 
        return sub_chunks
    
    encoded_str = long_str.encode('utf-8')
    current_byte_pos = 0
    while current_byte_pos < len(encoded_str):
        end_byte_pos = min(current_byte_pos + limit_b, len(encoded_str))
        byte_slice_candidate = encoded_str[current_byte_pos:end_byte_pos]
        
        while True:
            try:
                decoded_chunk = byte_slice_candidate.decode('utf-8')
                sub_chunks.append(decoded_chunk)
                current_byte_pos += len(byte_slice_candidate) 
                break 
            except UnicodeDecodeError:
                if len(byte_slice_candidate) > 1:
                    byte_slice_candidate = byte_slice_candidate[:-1] 
                else:
                    log(f"⚠️ Пропущен не декодируемый байт при принудительной нарезке: {encoded_str[current_byte_pos:current_byte_pos+1]!r}")
                    current_byte_pos += 1 
                    break 
    return sub_chunks


def smart_chunk(text_to_chunk, outer_limit_bytes):
    paragraphs = text_to_chunk.split("\n\n") 
    final_result_chunks = []
    current_accumulated_parts = [] 
    current_accumulated_bytes = 0  

    for para_idx, paragraph_str in enumerate(paragraphs):
        if not paragraph_str.strip(): 
            continue

        paragraph_bytes = paragraph_str.encode('utf-8')
        separator_bytes_len = 2 if current_accumulated_parts else 0 

        if current_accumulated_bytes + separator_bytes_len + len(paragraph_bytes) <= outer_limit_bytes:
            if current_accumulated_parts: 
                current_accumulated_parts.append("\n\n")
            current_accumulated_parts.append(paragraph_str)
            current_accumulated_bytes += separator_bytes_len + len(paragraph_bytes)
        else:
            if current_accumulated_parts:
                final_result_chunks.append("".join(current_accumulated_parts))
            
            current_accumulated_parts = []
            current_accumulated_bytes = 0

            if len(paragraph_bytes) > outer_limit_bytes:
                log(f"ℹ️ Абзац #{para_idx} '{paragraph_str[:30].replace(chr(10),' ')}...' слишком длинный ({len(paragraph_bytes)} байт > {outer_limit_bytes} байт), будет разрезан.")
                split_long_paragraph_sub_chunks = force_split_long_string(paragraph_str, outer_limit_bytes)
                final_result_chunks.extend(split_long_paragraph_sub_chunks) 
            else:
                current_accumulated_parts.append(paragraph_str)
                current_accumulated_bytes = len(paragraph_bytes)
                
    if current_accumulated_parts:
        final_result_chunks.append("".join(current_accumulated_parts))

    return [chunk_item for chunk_item in final_result_chunks if chunk_item.strip()]


def send(text_content, add_numeration_if_multiple_parts=False):
    prepared_text_content = prepare_text(str(text_content)) # Добавил str() для большей надежности
    
    prefix_max_allowance_bytes = 40 
    
    text_chunk_actual_limit_bytes = TG_LIMIT_BYTES 
    
    # Сначала делаем предварительную нарезку, чтобы узнать, сколько будет частей
    # Это нужно для корректного решения, применять ли уменьшенный лимит под префикс.
    # Если нумерация нужна (т.е. частей будет > 1), то лимит для smart_chunk должен быть меньше.
    limit_for_pre_chunking = TG_LIMIT_BYTES
    if add_numeration_if_multiple_parts: # Если в принципе нумерация может понадобиться
        limit_for_pre_chunking = TG_LIMIT_BYTES - prefix_max_allowance_bytes
        
    parts_list = smart_chunk(prepared_text_content, limit_for_pre_chunking)
    total_parts_count = len(parts_list)

    # Если нумерация должна быть, но частей всего одна, то для этой единственной части
    # можно использовать полный TG_LIMIT_BYTES, так как префикса "Часть 1/1" не будет.
    if add_numeration_if_multiple_parts and total_parts_count == 1:
        parts_list = smart_chunk(prepared_text_content, TG_LIMIT_BYTES) # Перенарезаем с полным лимитом
        total_parts_count = len(parts_list) # Должно остаться 1, если текст не слишком велик

    if not parts_list:
        log("ℹ️ Нет частей для отправки (текст пуст или состоит только из пробельных символов).")
        return

    for idx, single_part_content in enumerate(parts_list, 1):
        final_text_for_telegram = single_part_content
        log_part_prefix = "" 

        # Добавляем нумерацию "Часть X/Y", только если частей БОЛЬШЕ ОДНОЙ и флаг установлен
        if add_numeration_if_multiple_parts and total_parts_count > 1:
            numeration_prefix_str = f"Часть {idx}/{total_parts_count}:\n\n"
            final_text_for_telegram = numeration_prefix_str + single_part_content
            log_part_prefix = f"Часть {idx}/{total_parts_count} " 
            
            final_text_bytes_with_prefix = len(final_text_for_telegram.encode('utf-8'))
            if final_text_bytes_with_prefix > 4096:
                log(f"📛 ВНИМАНИЕ! {log_part_prefix}С ПРЕФИКСОМ СЛИШКОМ ДЛИННАЯ ({final_text_bytes_with_prefix} байт > 4096). Telegram ОБРЕЖЕТ ЭТУ ЧАСТЬ!")

        def make_telegram_api_call():
            return requests.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": CHANNEL_ID, "text": final_text_for_telegram, "disable_web_page_preview": True},
                timeout=15 
            )

        response_from_tg = safe_call(make_telegram_api_call, label=f"❗ Ошибка отправки {log_part_prefix}в TG")
        
        current_part_final_bytes = len(final_text_for_telegram.encode('utf-8'))
        current_part_final_chars = len(final_text_for_telegram)

        if response_from_tg and response_from_tg.status_code == 200:
            log(f"✅ {log_part_prefix}успешно отправлена ({current_part_final_bytes} байт, {current_part_final_chars} символов)")
        elif response_from_tg:
            error_text_preview = final_text_for_telegram[:150].replace('\n', ' ') 
            log(f"❗ Ошибка от Telegram для {log_part_prefix.strip()}: {response_from_tg.status_code} - {response_from_tg.text}")
            log(f"   Текст проблемной части (байты: {current_part_final_bytes}, символы: {current_part_final_chars}, начало): '{error_text_preview}...'")
        else: 
            error_text_preview = final_text_for_telegram[:150].replace('\n', ' ')
            log(f"❗ Не удалось отправить {log_part_prefix.strip()} (нет ответа от сервера Telegram после всех попыток).")
            log(f"   Текст проблемной части (байты: {current_part_final_bytes}, символы: {current_part_final_chars}, начало): '{error_text_preview}...'")

        if total_parts_count > 1 and idx < total_parts_count: 
            sleep_duration = 1.5 
            log(f"ℹ️ Пауза {sleep_duration} сек. перед следующей частью...")
            sleep(sleep_duration)

# --- Основная логика скрипта ---

def main():
    log("🚀 Скрипт запущен.")
    try:
        main_report_text_from_gpt = gpt_report() 
        
        list_of_report_components = [
            "📊 Рыночный отчёт", 
            main_report_text_from_gpt, # Уже .strip() из gpt_report()
            
            keyword_alert(main_report_text_from_gpt), 
            
            store_and_compare(main_report_text_from_gpt), 
            
            analyze_sentiment(main_report_text_from_gpt) 
        ]
        
        # Убираем None или пустые строки/строки из пробелов и затем объединяем
        valid_components = []
        for component in list_of_report_components:
            if isinstance(component, str) and component.strip():
                valid_components.append(component.strip()) # Дополнительно strip() для каждого компонента
            elif component is not None: # Если не строка, но не None, преобразуем в строку
                log(f"⚠️ Компонент отчета не является строкой, но не None: {type(component)}. Преобразован в строку.")
                str_component = str(component).strip()
                if str_component:
                    valid_components.append(str_component)
        
        full_report_final_string = "\n\n".join(valid_components)

        if full_report_final_string:
            send(full_report_final_string, add_numeration_if_multiple_parts=True)
            log("✅ Весь отчёт обработан и отправлен.")
        else:
            log("ℹ️ Итоговый отчет пуст, отправка не требуется.")

    except RuntimeError as e: 
        log(f"❌ Критическая ошибка при генерации GPT-отчета: {e}")
        sys.exit(1) 
    except requests.exceptions.RequestException as e: 
        log(f"❌ Критическая сетевая ошибка во время выполнения: {e}")
        log(traceback.format_exc())
        sys.exit(1)
    except Exception as e: 
        log(f"❌ Непредвиденная глобальная ошибка в main(): {e}")
        log(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main()