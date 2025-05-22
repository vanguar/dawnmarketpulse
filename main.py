#!/usr/bin/env python3
import pytz
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
from news_reader import get_news_block # Теперь возвращает кортеж (текст_новостей, есть_ли_новости)
from analyzer import keyword_alert, store_and_compare
from report_utils import analyze_sentiment

from metrics_reader import get_derivatives_block
#from whale_alert_reader import get_whale_activity_summary
from whale_alert_reader import get_whale_activity_summary
from fng_reader import get_fear_and_greed_index_text
from datetime import datetime, timezone, date, timedelta


# --- Конфигурация ---
openai.api_key = os.getenv("OPENAI_KEY")
TG_TOKEN = os.getenv("TG_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
MARKETAUX_KEY = os.getenv("MARKETAUX_KEY") # Убедитесь, что этот ключ тоже читается, если news_reader его использует

MODEL = "gpt-4o-mini"
TIMEOUT = 60
TG_LIMIT_BYTES = 3800 # Увеличено, подберите оптимальное значение
GPT_TOKENS = 1800 # Немного увеличено, если GPT обрезает ответы

# --- Промпты для GPT ---
GPT_CONTINUATION_WITH_NEWS = """Проанализируй предоставленные новости и далее дай сводку по следующим пунктам, фокусируясь на фондовом рынке и общих выводах:

Акции-лидеры 🚀 / Аутсайдеры 📉
- по 2–3 бумаги + причина (можно на основе новостей или общих знаний)

→ Вывод по фондовому рынку.

Макро-факторы и общие выводы (на основе предоставленных новостей и общих знаний):
- Ключевые моменты из новостей и их возможное влияние.
- Общий вывод по рыночной ситуации (затрагивая и фондовый, и крипторынок, если применимо).

Цитаты дня 🗣
- до 2 релевантных цитат + смысл (если есть подходящие из новостей или общие)

Число-факт 🤔 (интересный факт о рынках или экономике)

⚡️ Идея дня – 2 предложения actionable-совета.

‼️ Только обычный текст, без HTML и markdown. Не используй **жирный**, _курсив_, `код` или #заголовки.
‼️ Структурируй текст с ДВОЙНЫМИ переносами строк между абзацами.
‼️ Используй эмодзи перед заголовками разделов.
‼️ Данные по ценам криптовалют, индексам, лонгам/шортам и китовым переводам уже отображены отдельно. Твоя задача – анализ и дополнительные секции."""

GPT_CONTINUATION_NO_NEWS = """Дай сводку по следующим пунктам, основываясь на общих знаниях и текущей рыночной ситуации (новости за сегодня не предоставлены), фокусируясь на фондовом рынке и общих выводах:

Акции-лидеры 🚀 / Аутсайдеры 📉
- по 2–3 бумаги + причина

→ Вывод по фондовому рынку.

Общий вывод по рыночной ситуации (без конкретных новостей, на основе общих тенденций).

Цитаты дня 🗣
- до 2 релевантных цитат + смысл

Число-факт 🤔 (интересный факт о рынках или экономике)

⚡️ Идея дня – 2 предложения actionable-совета.

‼️ Только обычный текст, без HTML и markdown. Не используй **жирный**, _курсив_, `код` или #заголовки.
‼️ Структурируй текст с ДВОЙНЫМИ переносами строк между абзацами.
‼️ Используй эмодзи перед заголовками разделов.
‼️ Данные по ценам криптовалют, индексам, лонгам/шортам и китовым переводам уже отображены отдельно. Твоя задача – анализ и дополнительные секции."""


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
        except requests.exceptions.RequestException as e:
            log(f"{label}: попытка {i + 1}/{retries} не удалась - Ошибка сети: {e}")
            if i < retries - 1:
                sleep(delay)
        except Exception as e:
            log(f"{label}: попытка {i + 1}/{retries} не удалась - Общая ошибка: {e}")
            log(traceback.format_exc())
            if i < retries - 1:
                sleep(delay)
    log(f"{label}: все {retries} попытки провалены.")
    return None

# --- Сбор данных и генерация отчета ---

def gpt_report():
    today_date_str = date.today().strftime("%d.%m.%Y")
    
    # Получаем новости и флаг, есть ли они
    # get_news_block() из news_reader.py должен возвращать кортеж (текст_блока_новостей_для_GPT, флаг_наличия_реальных_новостей)
    news_text_for_gpt, has_actual_news = get_news_block() 

    header_for_gpt = f"📅 Анализ рыночной ситуации на {today_date_str}"
    current_gpt_continuation = ""
    
    if has_actual_news:
        log("📰 Обнаружены актуальные новости. Используется GPT_CONTINUATION_WITH_NEWS.")
        dynamic_data = (
            f"{header_for_gpt}\n\n"
            f"--- ПРЕДОСТАВЛЕННЫЕ НОВОСТИ РЫНКА (для твоего анализа) ---\n"
            f"{news_text_for_gpt}\n\n" 
            f"--- ЗАДАНИЕ ДЛЯ АНАЛИЗА ---\n"
            f"{GPT_CONTINUATION_WITH_NEWS}"
        )
        current_gpt_continuation = "WITH_NEWS"
    else:
        log("📰 Актуальные новости не найдены. Используется GPT_CONTINUATION_NO_NEWS.")
        dynamic_data = (
            f"{header_for_gpt}\n\n"
            f"(Обрати внимание: актуальные новости за сегодня не предоставлены. Пожалуйста, сделай анализ на основе общих знаний, где это применимо.)\n\n"
            f"--- ЗАДАНИЕ ДЛЯ АНАЛИЗА ---\n"
            f"{GPT_CONTINUATION_NO_NEWS}"
        )
        current_gpt_continuation = "NO_NEWS"
    
    log(f"ℹ️ Данные для GPT (длина): {len(dynamic_data)} символов. Промпт: {current_gpt_continuation}. Первые 200: {dynamic_data[:200]}...")

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
    log(f"📝 GPT сгенерировал аналитический текст ({len(generated_text)} символов).")
    return generated_text

# --- Обработка и отправка текста в Telegram ---
def prepare_text(text_to_prepare):
    if not isinstance(text_to_prepare, str):
        log(f"⚠️ prepare_text получил не строку: {type(text_to_prepare)}. Возвращаю как есть.")
        return str(text_to_prepare) 

    for marker in ["📊", "🚀", "📉", "₿", "📰", "🗣", "🤔", "⚡️", "🔍", "📈", "🧠", "⚖️", "🐋", "🤖"]: # Добавлены все используемые маркеры
        text_to_prepare = re.sub(f"({marker}[^\n]*)\n(?!\n)", r"\1\n\n", text_to_prepare)
    
    text_to_prepare = re.sub(r"(\n→[^\n]*)\n(?!\n)", r"\1\n\n", text_to_prepare) 
    
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
    prepared_text_content = prepare_text(str(text_content)) 
    
    prefix_max_allowance_bytes = 40 
    text_chunk_limit_for_smart_chunk = TG_LIMIT_BYTES 
    
    if add_numeration_if_multiple_parts:
        text_chunk_limit_for_smart_chunk = TG_LIMIT_BYTES - prefix_max_allowance_bytes
        
    parts_list = smart_chunk(prepared_text_content, text_chunk_limit_for_smart_chunk)
    total_parts_count = len(parts_list)

    if add_numeration_if_multiple_parts and total_parts_count == 1:
        log(f"ℹ️ Нумерация запрошена, но получилась 1 часть с лимитом {text_chunk_limit_for_smart_chunk}. Перенарезаем с полным лимитом {TG_LIMIT_BYTES}.")
        parts_list = smart_chunk(prepared_text_content, TG_LIMIT_BYTES) 
        total_parts_count = len(parts_list)

    if not parts_list:
        log("ℹ️ Нет частей для отправки (текст пуст или состоит только из пробельных символов).")
        return

    for idx, single_part_content in enumerate(parts_list, 1):
        final_text_for_telegram = single_part_content
        log_part_prefix_display = "" 

        if add_numeration_if_multiple_parts and total_parts_count > 1:
            numeration_prefix_str = f"Часть {idx}/{total_parts_count}:\n\n"
            final_text_for_telegram = numeration_prefix_str + single_part_content
            log_part_prefix_display = f"Часть {idx}/{total_parts_count} " 
            
            final_text_bytes_with_prefix = len(final_text_for_telegram.encode('utf-8'))
            if final_text_bytes_with_prefix > 4096: 
                log(f"📛 ВНИМАНИЕ! {log_part_prefix_display}С ПРЕФИКСОМ СЛИШКОМ ДЛИННАЯ ({final_text_bytes_with_prefix} байт > 4096). Telegram ОБРЕЖЕТ ЭТУ ЧАСТЬ!")

        def make_telegram_api_call():
            return requests.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": CHANNEL_ID, "text": final_text_for_telegram, "disable_web_page_preview": True},
                timeout=15 
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
        else: 
            error_text_preview = final_text_for_telegram[:150].replace('\n', ' ')
            log(f"❗ Не удалось отправить {log_part_prefix_display.strip()} (нет ответа от сервера Telegram после всех попыток).")
            log(f"   Текст проблемной части (байты: {current_part_final_bytes}, символы: {current_part_final_chars}, начало): '{error_text_preview}...'")

        if total_parts_count > 1 and idx < total_parts_count: 
            sleep_duration = 1.5 
            log(f"ℹ️ Пауза {sleep_duration} сек. перед следующей частью...")
            sleep(sleep_duration)

# --- Основная логика скрипта ---
def main():
    log("🚀 Скрипт запущен.")
    log(f"🔑 OPENAI_KEY: {'Установлен' if os.getenv('OPENAI_KEY') else 'НЕ УСТАНОВЛЕН!'}")
    log(f"🔑 WHALE_KEY: {'Установлен' if os.getenv('WHALE_KEY') else 'НЕ УСТАНОВЛЕН!'}")
    log(f"🔑 MARKETAUX_KEY: {'Установлен' if os.getenv('MARKETAUX_KEY') else 'НЕ УСТАНОВЛЕН!'}") # Добавил проверку ключа

    try:
        # 1. Сбор данных по КРИПТЕ (выводятся первыми)
        log("🔄 Сбор данных по криптовалютам...")
        crypto_price_block = get_crypto_data(extended=True) # Уже содержит заголовок "₿ Крипта на ДАТА"
        fear_and_greed_block = get_fear_and_greed_index_text()
        derivatives_block = get_derivatives_block() # Уже содержит заголовок "⚖️ Лонги / Шорты"
        
        log("🔄 Сбор данных по китовым транзакциям...")
        whale_activity_block = get_whale_activity_summary()
        log("🐋 Данные по китам получены.")

        # 2. Сбор данных по ФОНДОВОМУ РЫНКУ (выводятся вторыми)
        log("🔄 Сбор данных по фондовому рынку...")
        market_data_block = get_market_data_text() # Уже содержит заголовок "📊 Индексы"

        # 3. Генерация АНАЛИТИЧЕСКОЙ части от GPT
        # gpt_report() теперь сама решает, какой промпт использовать в зависимости от новостей
        log("🔄 Вызов GPT для генерации аналитической части отчета...")
        main_analytical_text_from_gpt = gpt_report()
        # Удаление Markdown
        main_analytical_text_from_gpt = re.sub(r"\*\*(.*?)\*\*", r"\1", main_analytical_text_from_gpt)
        main_analytical_text_from_gpt = re.sub(r"\_(.*?)\_", r"\1", main_analytical_text_from_gpt)
        main_analytical_text_from_gpt = re.sub(r"\`(.*?)\`", r"\1", main_analytical_text_from_gpt)
        main_analytical_text_from_gpt = re.sub(r"\#(.*?)\n", r"\1\n", main_analytical_text_from_gpt)
        log(f"📝 Получена аналитическая часть от GPT (длина {len(main_analytical_text_from_gpt)}).")

        # 4. Сборка ВСЕХ компонентов отчета в нужном порядке
        list_of_report_components = [
            # --- Блок КРИПТЫ ---
            crypto_price_block,
            fear_and_greed_block,  # 👈 вставка блока страха и жадности
            derivatives_block, 
            whale_activity_block,
            

            # --- Визуальный разделитель ---
            "______________________________", # <--- Твой разделитель

            # --- Блок ФОНДОВОГО РЫНКА ---
            market_data_block, 

            # --- Блок АНАЛИТИКИ от GPT ---
            # Добавляем общий заголовок для всего отчета перед выводом GPT
            f"🤖 Анализ и выводы от эксперта GPT на {date.today().strftime('%d.%m.%Y')}:",
            main_analytical_text_from_gpt,

            # В функции main() в main.py, при формировании list_of_report_components
            # ...
                # --- Дополнительные аналитические компоненты (относятся к тексту GPT) ---
                keyword_alert(main_analytical_text_from_gpt),
                store_and_compare(main_analytical_text_from_gpt),
                # analyze_sentiment(main_analytical_text_from_gpt) # <-- ЗАКОММЕНТИРУЙ ИЛИ УДАЛИ ЭТУ СТРОКУ
            # ... 
        ]
        
        # 5. Чистка и финальная сборка
        valid_components = []
        for component in list_of_report_components:
            if isinstance(component, str) and component.strip():
                valid_components.append(component.strip())
            elif component is not None:
                log(f"⚠️ Компонент отчета не строка: {type(component)}. Преобразован.")
                str_component = str(component).strip()
                if str_component:
                    valid_components.append(str_component)

        full_report_final_string = "\n\n".join(valid_components)
        # Добавляем общий заголовок для всего сообщения в Telegram
        now_eest = datetime.utcnow() + timedelta(hours=3)
        current_run_time_str = now_eest.strftime("%H:%M")
        run_log = f"⏱ Скрипт запущен по расписанию (время по Киеву: {current_run_time_str})"

        final_telegram_message = f"{run_log}\n\n⚡️ Momentum Pulse:\n\n{full_report_final_string}"

        # <<< НАЧАЛО ПРЕДЛАГАЕМОГО ДОБАВЛЕНИЯ >>>
        try:
            # Попытка получить время с указанием часового пояса из переменной окружения TZ
            # На Railway можно установить переменную окружения TZ, например, "Europe/Kiev"
            tz_name = os.getenv("TZ")
            if tz_name:
                user_timezone = timezone(pytz.timezone(tz_name).utcoffset(datetime.now()))
            else: # Фоллбэк на UTC+2, если TZ не задан
                user_timezone = timezone(timedelta(hours=2)) # Пример для UTC+2

            current_time_in_zone = datetime.now(user_timezone).strftime("%H:%M (%Z)")
            data_update_signature = f"\n\n---\n📅 Данные на ~ {date.today().strftime('%d.%m.%Y')}, обновлены около {current_time_in_zone}."
            final_telegram_message += data_update_signature
        except Exception as e:
            log(f"⚠️ Не удалось добавить временную метку с часовым поясом: {e}")
            # Фоллбэк на простое время без явной зоны, если что-то пошло не так с TZ
            current_time_simple = datetime.now().strftime("%H:%M")
            data_update_signature = f"\n\n---\n📅 Данные на ~ {date.today().strftime('%d.%m.%Y')}, обновлены около {current_time_simple}."
            final_telegram_message += data_update_signature
        # <<< КОНЕЦ ПРЕДЛАГАЕМОГО ДОБАВЛЕНИЯ >>>
        log(f"📄 Итоговый отчет собран (длина {len(final_telegram_message)}). Начало: {final_telegram_message[:200]}")

        # 6. Отправка в Telegram
        if final_telegram_message.strip() and final_telegram_message.strip() != "⚡️ DawnMarket Pulse:":
            log(f"📨 Отправка отчета в Telegram (TG_LIMIT_BYTES={TG_LIMIT_BYTES})...")
            send(final_telegram_message, add_numeration_if_multiple_parts=True)
            log("✅ Весь отчёт обработан и отправлен.")
        else:
            log("ℹ️ Итоговый отчет пуст или состоит только из пробельных символов (или только из заголовка), отправка не требуется.")

        sleep(3)
        log("⏳ Скрипт завершает работу после паузы.")

    except RuntimeError as e:
        log(f"❌ Критическая ошибка при генерации GPT-отчета: {e}")
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        log(f"❌ Сетевая ошибка: {e}")
        log(traceback.format_exc())
        sys.exit(1)
    except Exception as e:
        log(f"❌ Непредвиденная ошибка: {e}")
        log(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main()