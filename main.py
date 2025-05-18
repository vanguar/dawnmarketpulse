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
TG_LIMIT_BYTES = 1000 # <<<=== ОТЛАДОЧНОЕ ЗНАЧЕНИЕ ДЛЯ ТЕСТА РАЗБИВКИ
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

    # Гарантируем двойные переносы после маркеров-заголовков
    # Добавлены маркеры, используемые в main() для сборки full_report_string
    for marker in ["📊", "🚀", "📉", "₿", "📰", "🗣", "🤔", "⚡️", "🔍", "📈", "🧠"]:
        text_to_prepare = re.sub(f"({marker}[^\n]*)\n(?!\n)", r"\1\n\n", text_to_prepare)
    
    # Гарантируем двойные переносы после "→" в начале строки (если за ним текст до \n)
    text_to_prepare = re.sub(r"(\n→[^\n]*)\n(?!\n)", r"\1\n\n", text_to_prepare) 
    # Если "→" в конце строки, за ним уже есть \n, следующий абзац начнется с новой строки.
    # Можно добавить еще \n, если нужно именно два пустых переноса ПОСЛЕ стрелки, но обычно достаточно одного.
    # text_to_prepare = re.sub(r"(\n→)$", r"\1\n", text_to_prepare) # Если это нужно

    # Удаляем тройные и более переносы строк, заменяя их на двойные
    while "\n\n\n" in text_to_prepare:
        text_to_prepare = text_to_prepare.replace("\n\n\n", "\n\n")
    return text_to_prepare.strip()


def force_split_long_string(long_str, limit_b):
    """Безопасно режет длинную строку на части, не превышающие limit_b байт, сохраняя UTF-8."""
    sub_chunks = []
    if not long_str: # Если строка пустая, нечего делить
        return sub_chunks
    
    encoded_str = long_str.encode('utf-8')
    current_byte_pos = 0
    while current_byte_pos < len(encoded_str):
        # Определяем конец текущего среза байтов
        end_byte_pos = min(current_byte_pos + limit_b, len(encoded_str))
        byte_slice_candidate = encoded_str[current_byte_pos:end_byte_pos]
        
        # Пытаемся декодировать, отступая по одному байту назад при ошибке,
        # чтобы не разрезать многобайтовый символ посередине.
        while True:
            try:
                decoded_chunk = byte_slice_candidate.decode('utf-8')
                sub_chunks.append(decoded_chunk)
                current_byte_pos += len(byte_slice_candidate) # Перемещаем указатель на длину успешно обработанных байтов
                break # Выходим из внутреннего цикла (while True)
            except UnicodeDecodeError:
                if len(byte_slice_candidate) > 1:
                    byte_slice_candidate = byte_slice_candidate[:-1] # Уменьшаем срез на 1 байт
                else:
                    # Не удалось декодировать даже 1 байт (очень редкий/ошибочный сценарий)
                    log(f"⚠️ Пропущен не декодируемый байт при принудительной нарезке: {encoded_str[current_byte_pos:current_byte_pos+1]!r}")
                    current_byte_pos += 1 # Пропускаем этот байт и пытаемся снова
                    break # Выходим из внутреннего цикла
    return sub_chunks


def smart_chunk(text_to_chunk, outer_limit_bytes):
    """Разбивает текст на чанки с учетом байтового лимита, стараясь сохранять абзацы."""
    paragraphs = text_to_chunk.split("\n\n") # Разделяем текст на абзацы
    final_result_chunks = []
    current_accumulated_parts = [] # Список строк для текущего собираемого чанка
    current_accumulated_bytes = 0  # Байтовая длина current_accumulated_parts

    for para_idx, paragraph_str in enumerate(paragraphs):
        if not paragraph_str.strip(): # Пропускаем полностью пустые абзацы
            continue

        paragraph_bytes = paragraph_str.encode('utf-8')
        # Длина разделителя "\n\n" (2 байта), если это не первый абзац в текущем чанке
        separator_bytes_len = 2 if current_accumulated_parts else 0 

        if current_accumulated_bytes + separator_bytes_len + len(paragraph_bytes) <= outer_limit_bytes:
            # Текущий абзац помещается в собираемый чанк
            if current_accumulated_parts: # Если в чанке уже есть части, добавляем разделитель
                current_accumulated_parts.append("\n\n")
            current_accumulated_parts.append(paragraph_str)
            current_accumulated_bytes += separator_bytes_len + len(paragraph_bytes)
        else:
            # Текущий абзац не помещается.
            # Сначала сохраняем то, что уже накоплено в current_accumulated_parts (если там что-то есть).
            if current_accumulated_parts:
                final_result_chunks.append("".join(current_accumulated_parts))
            
            # Сбрасываем текущий собираемый чанк
            current_accumulated_parts = []
            current_accumulated_bytes = 0

            # Теперь обрабатываем paragraph_str, который не поместился
            if len(paragraph_bytes) > outer_limit_bytes:
                # Сам абзац длиннее лимита, его нужно принудительно резать
                log(f"ℹ️ Абзац #{para_idx} '{paragraph_str[:30].replace(chr(10),' ')}...' слишком длинный ({len(paragraph_bytes)} байт > {outer_limit_bytes} байт), будет разрезан.")
                split_long_paragraph_sub_chunks = force_split_long_string(paragraph_str, outer_limit_bytes)
                final_result_chunks.extend(split_long_paragraph_sub_chunks) # Каждый кусок длинного абзаца - это новый чанк
            else:
                # Абзац сам по себе не длиннее лимита, но не влез в предыдущий собираемый чанк.
                # Он становится началом нового собираемого чанка.
                current_accumulated_parts.append(paragraph_str)
                current_accumulated_bytes = len(paragraph_bytes)
                
    # Добавляем последний накопленный чанк, если он не пуст
    if current_accumulated_parts:
        final_result_chunks.append("".join(current_accumulated_parts))

    return [chunk_item for chunk_item in final_result_chunks if chunk_item.strip()] # Удаляем полностью пустые чанки, если образовались


def send(text_content, add_numeration_if_multiple_parts=False):
    prepared_text_content = prepare_text(str(text_content)) 
    
    prefix_max_allowance_bytes = 40 
    
    # Лимит для самого текста части, ДО добавления префикса
    text_chunk_limit_for_smart_chunk = TG_LIMIT_BYTES # По умолчанию (если нумерация не нужна или часть одна)
    
    # Если нумерация потенциально нужна (т.е. add_numeration_if_multiple_parts=True),
    # то для предварительной нарезки и подсчета частей используем уменьшенный лимит.
    if add_numeration_if_multiple_parts:
        text_chunk_limit_for_smart_chunk = TG_LIMIT_BYTES - prefix_max_allowance_bytes
        
    parts_list = smart_chunk(prepared_text_content, text_chunk_limit_for_smart_chunk)
    total_parts_count = len(parts_list)

    # Если нумерация была запрошена, но по факту получилась только одна часть
    # (из-за уменьшенного лимита на этапе предварительной нарезки),
    # то перенарезаем эту единственную часть с полным лимитом, т.к. префикс "Часть 1/1" не будет добавлен.
    if add_numeration_if_multiple_parts and total_parts_count == 1:
        log(f"ℹ️ Нумерация запрошена, но получилась 1 часть с лимитом {text_chunk_limit_for_smart_chunk}. Перенарезаем с полным лимитом {TG_LIMIT_BYTES}.")
        parts_list = smart_chunk(prepared_text_content, TG_LIMIT_BYTES) 
        total_parts_count = len(parts_list) # Должно остаться 1, если текст не слишком велик для полного лимита

    if not parts_list:
        log("ℹ️ Нет частей для отправки (текст пуст или состоит только из пробельных символов).")
        return

    for idx, single_part_content in enumerate(parts_list, 1):
        final_text_for_telegram = single_part_content
        log_part_prefix_display = "" # Для отображения в логах

        # Добавляем нумерацию "Часть X/Y", только если частей БОЛЬШE ОДНОЙ и флаг add_numeration_if_multiple_parts установлен
        if add_numeration_if_multiple_parts and total_parts_count > 1:
            numeration_prefix_str = f"Часть {idx}/{total_parts_count}:\n\n"
            final_text_for_telegram = numeration_prefix_str + single_part_content
            log_part_prefix_display = f"Часть {idx}/{total_parts_count} " # Для лога
            
            # Финальная проверка байтовой длины уже С ПРЕФИКСОМ перед отправкой
            final_text_bytes_with_prefix = len(final_text_for_telegram.encode('utf-8'))
            if final_text_bytes_with_prefix > 4096: # Абсолютный лимит Telegram
                log(f"📛 ВНИМАНИЕ! {log_part_prefix_display}С ПРЕФИКСОМ СЛИШКОМ ДЛИННАЯ ({final_text_bytes_with_prefix} байт > 4096). Telegram ОБРЕЖЕТ ЭТУ ЧАСТЬ!")
                # Если это происходит, TG_LIMIT_BYTES и/или prefix_max_allowance_bytes нужно уменьшать.

        def make_telegram_api_call():
            # Эта вложенная функция нужна для safe_call
            return requests.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": CHANNEL_ID, "text": final_text_for_telegram, "disable_web_page_preview": True},
                timeout=15 # Таймаут на один запрос к Telegram
            )

        response_from_tg = safe_call(make_telegram_api_call, label=f"❗ Ошибка отправки {log_part_prefix_display}в TG")
        
        current_part_final_bytes = len(final_text_for_telegram.encode('utf-8'))
        current_part_final_chars = len(final_text_for_telegram)

        if response_from_tg and response_from_tg.status_code == 200:
            log(f"✅ {log_part_prefix_display}успешно отправлена ({current_part_final_bytes} байт, {current_part_final_chars} символов)")
        elif response_from_tg:
            error_text_preview = final_text_for_telegram[:150].replace('\n', ' ') 
            log(f"❗ Ошибка от Telegram для {log_part_prefix_display.strip()}: {response_from_tg.status_code} - {response_from_tg.text}")
            log(f"   Текст проблемной части (байты: {current_part_final_bytes}, символы: {current_part_final_chars}, начало): '{error_text_preview}...'")
        else: # safe_call вернул None
            error_text_preview = final_text_for_telegram[:150].replace('\n', ' ')
            log(f"❗ Не удалось отправить {log_part_prefix_display.strip()} (нет ответа от сервера Telegram после всех попыток).")
            log(f"   Текст проблемной части (байты: {current_part_final_bytes}, символы: {current_part_final_chars}, начало): '{error_text_preview}...'")

        # Пауза между отправкой частей, если их несколько
        if total_parts_count > 1 and idx < total_parts_count: 
            sleep_duration = 1.5 
            log(f"ℹ️ Пауза {sleep_duration} сек. перед следующей частью...")
            sleep(sleep_duration)

# --- Основная логика скрипта ---

def main():
    log("🚀 Скрипт запущен.")
    try:
        # 1. Генерируем основной текстовый отчет от GPT
        main_report_text_from_gpt = gpt_report() 
        
        # 2. Собираем все компоненты отчета
        # Каждая функция-компонент (keyword_alert и т.д.) должна возвращать строку
        # уже с необходимыми заголовками и форматированием (например, начинаться с эмодзи-маркера).
        
        list_of_report_components = [
            "📊 Рыночный отчёт", # Добавляем общий заголовок для GPT отчета
            main_report_text_from_gpt,
            
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

        # 3. Отправляем собранный отчет в Telegram
        if full_report_final_string:
            # Нумерация "Часть X/Y" будет добавлена, только если частей окажется больше одной.
            send(full_report_final_string, add_numeration_if_multiple_parts=True)
            log("✅ Весь отчёт обработан и отправлен.")
        else:
            log("ℹ️ Итоговый отчет пуст или состоит только из пробельных символов, отправка не требуется.")

    except RuntimeError as e: # Ошибка от OpenAI (например, "OpenAI не ответил")
        log(f"❌ Критическая ошибка при генерации GPT-отчета: {e}")
        sys.exit(1) 
    except requests.exceptions.RequestException as e: # Ошибки сети (DNS, Connection refused и т.д.)
        log(f"❌ Критическая сетевая ошибка во время выполнения: {e}")
        log(traceback.format_exc())
        sys.exit(1)
    except Exception as e: # Любые другие непредвиденные ошибки
        log(f"❌ Непредвиденная глобальная ошибка в main(): {e}")
        log(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main()