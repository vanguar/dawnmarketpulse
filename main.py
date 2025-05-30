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
from datetime import datetime, timezone, date, timedelta
from time import sleep
import traceback
import re

# Модули проекта
from market_reader import get_market_data_text, get_crypto_data
# Импортируем обновленные функции и список инфлюенсеров
from news_reader import get_news_block, get_news_pool_for_gpt_analysis, INFLUENCERS_TO_TRACK
from analyzer import keyword_alert, store_and_compare
from metrics_reader import get_derivatives_block
from whale_alert_reader import get_whale_activity_summary
from fng_reader import get_fear_and_greed_index_text
from collections import Counter
from custom_logger import log


# --- Конфигурация ---
openai.api_key = os.getenv("OPENAI_KEY")
TG_TOKEN = os.getenv("TG_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
MARKETAUX_KEY = os.getenv("MARKETAUX_KEY")
COINMARKETCAP_KEY = os.getenv("COINMARKETCAP_KEY")

MODEL = "gpt-4o-mini"
TIMEOUT = 120 
TG_LIMIT_BYTES = 3800
GPT_TOKENS_MAIN_ANALYSIS = 1800 
GPT_TOKENS_INFLUENCER_ANALYSIS = 800


# --- Промпты для GPT (основной анализ - с усиленными инструкциями) ---
GPT_CONTINUATION_WITH_NEWS = """⚠️ ВАЖНО: НЕ ПОВТОРЯЙ информацию, которая уже была упомянута в предыдущих пунктах или в предоставленных новостях. Каждый раздел твоего ответа должен содержать УНИКАЛЬНУЮ информацию.
Проанализируй предоставленные новости и дай ЛАКОНИЧНУЮ сводку:
Акции-лидеры 🚀 / Аутсайдеры 📉
- 2–3 бумаги с краткой причиной.
Ключевые новости и влияние 📰
- Суть без пересказов, только возможное влияние.
→ Общий вывод 🌍
- Краткий обзор фондового и крипторынка. Без повторов из предыдущих пунктов твоего ответа.
Цитаты дня 🗣
- До 2 цитат и краткий смысл.
Число-факт 🤔
- Один интересный факт.
⚡️ Идея дня
- Один короткий совет.
‼️ Без HTML, Markdown. Двойные переносы строк. Используй эмодзи как в примере.
"""

GPT_CONTINUATION_NO_NEWS = """⚠️ ВАЖНО: НЕ ПОВТОРЯЙ информацию, которая уже была упомянута в предыдущих пунктах. Каждый раздел твоего ответа должен содержать УНИКАЛЬНУЮ информацию.
Дай ЛАКОНИЧНУЮ сводку по рынку (без новостей):
Акции-лидеры 🚀 / Аутсайдеры 📉
- 2–3 бумаги и краткая причина.
→ Общий вывод 🌍
- Что происходит на рынках и почему. Без воды и без повторов из предыдущих пунктов твоего ответа.
Цитаты дня 🗣
- До 2 цитат и краткий смысл.
Число-факт 🤔
- Один интересный факт.
⚡️ Идея дня
- Один краткий actionable совет.
‼️ Без HTML, Markdown. Двойные переносы строк. Используй эмодзи как в примере.
"""

# --- ОБНОВЛЕННЫЙ ПРОМПТ для анализа упоминаний влиятельных лиц (с усиленной инструкцией) ---
GPT_INFLUENCER_ANALYSIS_PROMPT = """⚠️ ВАЖНО: Каждый раздел твоего ответа (например, "Ключевые моменты" и "Аналитический вывод") должен содержать УНИКАЛЬНУЮ информацию и не повторять дословно формулировки из других разделов твоего же ответа. Аналитический вывод должен быть именно выводом, а не пересказом найденных упоминаний.

Тебе предоставлен список влиятельных лиц и блок общих новостей за последнее время.
Твоя задача:
1. Внимательно просмотри предоставленный ОБЩИЙ БЛОК НОВОСТЕЙ.
2. Найди в этих новостях любые ПРЯМЫЕ или ЯВНЫЕ КОСВЕННЫЕ УПОМИНАНИЯ (высказывания, действия, значимые новости), относящиеся к кому-либо из следующего списка лиц: {influencer_names_list}.
3. Если упоминания найдены:
    а. Из всех найденных упоминаний выбери 1-2 НАИБОЛЕЕ ВАЖНЫХ для финансовых рынков (фондовый, криптовалютный) или ключевых технологических трендов. Отдавай предпочтение конкретным высказываниям или анонсам, а не просто факту упоминания имени.
    б. Для каждого выбранного важного упоминания кратко изложи его суть (например, "Илон Маск заявил о..." или "Новость о Сэме Альтмане указывает на...").
    в. Дай ОБЩИЙ АНАЛИТИЧЕСКИЙ ВЫВОД (2-4 предложения) по этим выделенным моментам: что они могут означать для инвесторов, каковы возможные последствия, на что обратить внимание. Этот вывод должен быть твоим собственным анализом, а не простым повторением сути упоминаний.
4. Если среди предоставленных общих новостей ЗНАЧИМЫХ упоминаний указанных лиц (которые могли бы повлиять на рынки) НЕ НАЙДЕНО, или найденные упоминания не несут рыночной значимости, напиши: "В сегодняшней подборке общих новостей значимых публичных заявлений или новостей, связанных с отслеживаемыми влиятельными лицами и способных повлиять на рынки, не обнаружено."

Формат ответа (если найдены значимые упоминания):
Ключевые моменты от влиятельных лиц (из общих новостей):
- Про [Имя Фамилия]: [Суть важного упоминания 1]
- Про [Имя Фамилия]: [Суть важного упоминания 2 (если есть)]
Аналитический вывод: [Твой вывод, синтезирующий информацию, а не повторяющий её]

Формат ответа (если не найдено значимых упоминаний):
[Сообщение об отсутствии значимых упоминаний, как указано в пункте 4]

‼️ Используй только обычный текст. Без Markdown. Будь максимально краток и сфокусирован на потенциальном влиянии. Избегай общих фраз, если нет конкретики. Игнорируй новости из предоставленного пула, которые не содержат релевантной информации об указанных лицах или их деятельности, или если их упоминание не имеет рыночного значения.

СПИСОК ВЛИЯТЕЛЬНЫХ ЛИЦ ДЛЯ ПОИСКА:
{influencer_names_list}

ОБЩИЙ БЛОК НОВОСТЕЙ ДЛЯ АНАЛИЗА (обрати внимание, это не отфильтрованные новости, тебе нужно самому найти в них упоминания указанных лиц):
---
{general_news_text_pool}
---

Твой анализ:
"""

# --- Вспомогательные функции (log, safe_call - без изменений) ---
def log(msg):
    timestamp = f"[{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC]"
    print(f"{timestamp} {msg}", flush=True)

def safe_call(func, retries=3, delay=5, label="❗ Ошибка"):
    for i in range(retries):
        try:
            return func()
        except requests.exceptions.Timeout:
            log(f"{label}: попытка {i + 1}/{retries} не удалась - Таймаут ({TIMEOUT}с)")
        except requests.exceptions.RequestException as e:
            log(f"{label}: попытка {i + 1}/{retries} не удалась - Ошибка сети: {e}")
        except openai.error.OpenAIError as e: 
            log(f"{label} OpenAI: попытка {i + 1}/{retries} не удалась - {type(e).__name__}: {e}")
        except Exception as e:
            log(f"{label}: попытка {i + 1}/{retries} не удалась - Общая ошибка: {type(e).__name__} - {e}")
            # log(traceback.format_exc()) 
        if i < retries - 1:
            log(f"Пауза {delay} сек. перед следующей попыткой...")
            sleep(delay)
    log(f"{label}: все {retries} попытки провалены.")
    return None

# --- Генерация основного отчета GPT (gpt_report - без изменений) ---
def gpt_report():
    today_date_str = date.today().strftime("%d.%m.%Y")
    news_text_for_gpt, has_actual_news = get_news_block() 
    header_for_gpt = f"📅 Анализ рыночной ситуации на {today_date_str}"
    current_gpt_prompt_name = ""
    
    if has_actual_news:
        log("📰 Обнаружены актуальные новости для основного анализа. Используется GPT_CONTINUATION_WITH_NEWS.")
        prompt_content = GPT_CONTINUATION_WITH_NEWS
        current_gpt_prompt_name = "WITH_NEWS"
        dynamic_data_for_gpt = (
            f"{header_for_gpt}\n\n"
            f"--- ПРЕДОСТАВЛЕННЫЕ НОВОСТИ РЫНКА (для основного анализа) ---\n"
            f"{news_text_for_gpt}\n\n" 
            f"--- ЗАДАНИЕ ДЛЯ АНАЛИЗА ---\n"
            f"{prompt_content}"
        )
    else:
        log("📰 Актуальные новости для основного анализа не найдены. Используется GPT_CONTINUATION_NO_NEWS.")
        prompt_content = GPT_CONTINUATION_NO_NEWS
        current_gpt_prompt_name = "NO_NEWS"
        dynamic_data_for_gpt = (
            f"{header_for_gpt}\n\n"
            f"(Обрати внимание: актуальные новости для основного анализа за сегодня не предоставлены.)\n\n"
            f"--- ЗАДАНИЕ ДЛЯ АНАЛИЗА ---\n"
            f"{prompt_content}"
        )
    
    log(f"ℹ️ Данные для GPT (основной анализ, длина: {len(dynamic_data_for_gpt)}). Промпт: {current_gpt_prompt_name}. Начало: {dynamic_data_for_gpt[:200].replace(chr(10), ' ')}...")
    response = safe_call(
        lambda: openai.ChatCompletion.create(
            model=MODEL,
            messages=[{"role": "user", "content": dynamic_data_for_gpt}],
            timeout=TIMEOUT, 
            temperature=0.4,
            max_tokens=GPT_TOKENS_MAIN_ANALYSIS,
        ),
        label="❗ Ошибка OpenAI (основной анализ)"
    )
    if not response or not response.choices:
        log("❌ OpenAI не ответил на основной запрос или вернул пустой ответ.")
        return "🤖 Не удалось получить основной аналитический отчет от GPT." 
    
    generated_text = response.choices[0].message.content.strip()
    log(f"📝 GPT сгенерировал основной аналитический текст ({len(generated_text)}).")
    return generated_text

# --- ОБНОВЛЕННАЯ ФУНКЦИЯ для анализа упоминаний инфлюенсеров (с поиском в общем тексте) ---
def analyze_influencer_mentions_with_gpt(general_news_pool_text, influencer_list):
    """
    Ищет упоминания влиятельных лиц в общем пуле новостей и анализирует их с помощью GPT.
    """
    if not general_news_pool_text or \
       "не удалось загрузить пул" in general_news_pool_text.lower() or \
       "ключ marketaux api не настроен" in general_news_pool_text.lower() or \
       "ошибка при загрузке пула новостей" in general_news_pool_text.lower(): # Добавлена проверка на общую ошибку
        log(f"ℹ️ Нет пула новостей для анализа упоминаний инфлюенсеров или ошибка загрузки. Текст: {general_news_pool_text}")
        return general_news_pool_text 

    influencer_names_str = ", ".join([p['name'] for p in influencer_list])
    if not influencer_names_str:
        log("⚠️ Список инфлюенсеров для анализа пуст.")
        return "⚠️ Список отслеживаемых влиятельных лиц не определен."

    prompt = GPT_INFLUENCER_ANALYSIS_PROMPT.format(
        influencer_names_list=influencer_names_str,
        general_news_text_pool=general_news_pool_text
    )
    
    log(f"ℹ️ Данные для GPT (анализ инфлюенсеров, длина промпта: {len(prompt)}). Имена для поиска: {influencer_names_str}. Начало пула новостей: {general_news_pool_text[:200].replace(chr(10), ' ')}...")
    response = safe_call(
        lambda: openai.ChatCompletion.create(
            model=MODEL, 
            messages=[{"role": "user", "content": prompt}],
            timeout=TIMEOUT + 30, 
            temperature=0.5, 
            max_tokens=GPT_TOKENS_INFLUENCER_ANALYSIS 
        ),
        label="❗ Ошибка OpenAI (анализ инфлюенсеров)"
    )

    if not response or not response.choices:
        log("❌ OpenAI не ответил на запрос анализа инфлюенсеров или вернул пустой ответ.")
        return "🤖 Не удалось получить анализ упоминаний влиятельных лиц от GPT (OpenAI не ответил)."
    
    analysis_text = response.choices[0].message.content.strip()
    log(f"📝 GPT сгенерировал анализ по инфлюенсерам ({len(analysis_text)}).")
    return analysis_text


# --- Обработка и отправка текста в Telegram (prepare_text, force_split_long_string, smart_chunk, send - без изменений) ---
def prepare_text(text_to_prepare):
    if not isinstance(text_to_prepare, str):
        log(f"⚠️ prepare_text получил не строку: {type(text_to_prepare)}. Возвращаю как есть.")
        return str(text_to_prepare) 
    text_to_prepare = re.sub(r'\n{3,}', '\n\n', text_to_prepare.strip())
    section_markers_regex = r"^([📊🚀📉₿📰🗣🤔⚡️🔍📈🧠⚖️🐋🤖🌍💡⏱📅💬].*)"
    lines = text_to_prepare.split('\n')
    processed_lines = []
    for i, line in enumerate(lines):
        stripped_line = line.strip()
        if not stripped_line: 
            if not processed_lines or processed_lines[-1].strip(): 
                processed_lines.append("")
            continue
        processed_lines.append(line)
        if re.match(section_markers_regex, stripped_line):
            if i + 1 < len(lines) and lines[i+1].strip(): 
                processed_lines.append("") 
    final_text = "\n".join(processed_lines)
    return re.sub(r'\n{3,}', '\n\n', final_text).strip()


def force_split_long_string(long_str, limit_b):
    sub_chunks = []
    if not long_str: return sub_chunks
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
        if not paragraph_str.strip(): continue
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
                log(f"ℹ️ Абзац #{para_idx} '{paragraph_str[:30].replace(chr(10),' ')}...' ({len(paragraph_bytes)}Б > {outer_limit_bytes}Б) будет разрезан.")
                split_long_paragraph_sub_chunks = force_split_long_string(paragraph_str, outer_limit_bytes)
                if split_long_paragraph_sub_chunks:
                    final_result_chunks.extend(split_long_paragraph_sub_chunks[:-1])
                    current_accumulated_parts.append(split_long_paragraph_sub_chunks[-1])
                    current_accumulated_bytes = len(split_long_paragraph_sub_chunks[-1].encode('utf-8'))
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
        parts_list = smart_chunk(prepared_text_content, TG_LIMIT_BYTES) 
        total_parts_count = len(parts_list)
    if not parts_list:
        log("ℹ️ Нет частей для отправки.")
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
                log(f"📛 ВНИМАНИЕ! {log_part_prefix_display}С ПРЕФИКСОМ СЛИШКОМ ДЛИННАЯ ({final_text_bytes_with_prefix}Б > 4096Б). Telegram ОБРЕЖЕТ ЭТУ ЧАСТЬ!")
        def make_telegram_api_call():
            return requests.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": CHANNEL_ID, "text": final_text_for_telegram, "disable_web_page_preview": True, "parse_mode": "HTML"},
                timeout=20 
            )
        response_from_tg = safe_call(make_telegram_api_call, label=f"❗ Ошибка отправки {log_part_prefix_display}в TG")
        current_part_final_bytes = len(final_text_for_telegram.encode('utf-8'))
        current_part_final_chars = len(final_text_for_telegram)
        if response_from_tg and response_from_tg.status_code == 200:
            log(f"✅ {log_part_prefix_display}успешно отправлена ({current_part_final_bytes}Б, {current_part_final_chars} симв.)")
        elif response_from_tg:
            error_text_preview = final_text_for_telegram[:150].replace('\n', ' ') 
            log(f"❗ Ошибка от Telegram для {log_part_prefix_display.strip()}: {response_from_tg.status_code} - {response_from_tg.text}")
            log(f"   Текст проблемной части (байты: {current_part_final_bytes}, симв: {current_part_final_chars}, начало): '{error_text_preview}...'")
        else: 
            error_text_preview = final_text_for_telegram[:150].replace('\n', ' ')
            log(f"❗ Не удалось отправить {log_part_prefix_display.strip()} (нет ответа от сервера Telegram).")
            log(f"   Текст проблемной части (байты: {current_part_final_bytes}, симв: {current_part_final_chars}, начало): '{error_text_preview}...'")
        if total_parts_count > 1 and idx < total_parts_count: 
            sleep_duration = 1.5 
            log(f"ℹ️ Пауза {sleep_duration} сек. перед следующей частью...")
            sleep(sleep_duration)

# --- Основная логика скрипта ---
def main():
    log("🚀 Скрипт запущен.")
    required_keys = ["OPENAI_KEY", "TG_TOKEN", "CHANNEL_ID", "MARKETAUX_KEY", "COINMARKETCAP_KEY"]
    keys_ok = True
    for key_name in required_keys:
        if not os.getenv(key_name):
            log(f"📛 Ключ API {key_name} НЕ УСТАНОВЛЕН! Скрипт не может продолжить работу.")
            keys_ok = False
        else:
            log(f"🔑 Ключ API {key_name}: Установлен.")
    if not keys_ok:
        sys.exit("Ошибка: Отсутствуют необходимые ключи API.")

    try:
        tz_name_env = os.getenv("TZ", "Europe/Kiev") 
        try:
            user_timezone = pytz.timezone(tz_name_env)
            now_in_zone = datetime.now(user_timezone)
        except pytz.exceptions.UnknownTimeZoneError:
            log(f"⚠️ Неизвестный часовой пояс в TZ='{tz_name_env}'. Используется UTC.")
            user_timezone = timezone.utc
            now_in_zone = datetime.now(user_timezone)
            
        current_run_time_str = now_in_zone.strftime("%H:%M")
        current_date_str = now_in_zone.strftime('%d.%m.%Y')
        update_time_str = now_in_zone.strftime("%H:%M (%Z)")

        run_log_msg = f"⏱ Скрипт запущен ({current_run_time_str} {now_in_zone.strftime('%Z')})"
        report_title_msg = "⚡️ Momentum Pulse:"
        
        # 1. Сбор основных данных
        log("🔄 Сбор данных по криптовалютам...")
        crypto_price_block = get_crypto_data(extended=True) 
        fear_and_greed_block = get_fear_and_greed_index_text()
        derivatives_block = get_derivatives_block() 
        
        log("🔄 Сбор данных по китовым транзакциям...")
        whale_activity_block = get_whale_activity_summary()
        log("🐋 Данные по китам: " + ("Получены." if whale_activity_block and "Ошибка" not in whale_activity_block else "Не удалось получить или ошибка."))

        log("🔄 Сбор данных по фондовому рынку...")
        market_data_block = get_market_data_text()

        # 2. Получение пула новостей и анализ упоминаний влиятельных лиц
        log("🔄 Загрузка пула новостей для поиска упоминаний влиятельных лиц...")
        general_news_pool = get_news_pool_for_gpt_analysis() # Эта функция теперь возвращает пул новостей или сообщение об ошибке
        
        influencer_final_analysis_block = "" 
        # Вызываем анализ GPT, только если general_news_pool не содержит сообщения об ошибке
        if general_news_pool and \
           "не удалось загрузить пул" not in general_news_pool.lower() and \
           "ключ marketaux api не настроен" not in general_news_pool.lower() and \
           "ошибка при загрузке пула новостей" not in general_news_pool.lower():
            log("🔄 Анализ упоминаний влиятельных лиц с помощью GPT...")
            gpt_analysis_of_mentions = analyze_influencer_mentions_with_gpt(general_news_pool, INFLUENCERS_TO_TRACK) # INFLUENCERS_TO_TRACK импортирован из news_reader
            
            if gpt_analysis_of_mentions:
                # Проверяем, не является ли результат просто сообщением об ошибке от GPT или "не найдено"
                if "не удалось получить анализ" in gpt_analysis_of_mentions.lower() or \
                   "не найдено" in gpt_analysis_of_mentions.lower() or \
                   "не обнаружено" in gpt_analysis_of_mentions.lower(): # Добавлено "не обнаружено"
                    influencer_final_analysis_block = f"🗣️ {gpt_analysis_of_mentions}" 
                else:
                    influencer_final_analysis_block = f"💬 Мнения лидеров и их анализ от GPT:\n{gpt_analysis_of_mentions}"
        else: # Если была ошибка при загрузке пула новостей
            influencer_final_analysis_block = general_news_pool # Отображаем сообщение об ошибке/отсутствии данных от get_news_pool_for_gpt_analysis

        # 3. Генерация ОСНОВНОЙ АНАЛИТИЧЕСКОЙ части от GPT
        log("🔄 Вызов GPT для генерации основного аналитического отчета...")
        main_analytical_text_from_gpt = gpt_report()
        main_analytical_text_from_gpt = re.sub(r"[\*_`#]", "", main_analytical_text_from_gpt) 
        log(f"📝 Получена основная аналитическая часть от GPT (длина {len(main_analytical_text_from_gpt)}).")

        # ---> НАЧАЛО БЛОКА ДЕДУПЛИКАЦИИ (ИНТЕГРИРОВАННЫЙ БЛОК) <---
        if main_analytical_text_from_gpt.strip(): # Проверяем, что текст не пустой
            log("ℹ️ Выполняется дедупликация строк в аналитическом блоке GPT...")
            lines_gpt = main_analytical_text_from_gpt.splitlines()
            filtered_lines_gpt = []
            seen_gpt_lines = Counter() # Используем другое имя для счетчика
            for line_gpt in lines_gpt:
                stripped_line_content = line_gpt.strip()
                # Добавляем строку, если она не пустая и мы ее еще не видели
                if stripped_line_content and seen_gpt_lines[stripped_line_content] == 0:
                    filtered_lines_gpt.append(line_gpt)
                # Или если строка пустая (сохраняем для форматирования абзацев)
                elif not stripped_line_content:
                    filtered_lines_gpt.append(line_gpt)
                seen_gpt_lines[stripped_line_content] += 1
            
            original_len = len(main_analytical_text_from_gpt)
            main_analytical_text_from_gpt = "\n".join(filtered_lines_gpt)
            new_len = len(main_analytical_text_from_gpt)
            if original_len != new_len:
                log(f"ℹ️ Дедупликация завершена. Длина текста GPT изменена с {original_len} на {new_len} символов.")
            else:
                log(f"ℹ️ Дедупликация завершена. Повторяющихся строк в тексте GPT не найдено.")
        else:
            log("ℹ️ Аналитический блок GPT пуст, дедупликация не требуется.")
        # ---> КОНЕЦ БЛОКА ДЕДУПЛИКАЦИИ <---

        # 4. Сборка ВСЕХ компонентов отчета
        list_of_report_components = [
            run_log_msg,
            report_title_msg,
            crypto_price_block,
            fear_and_greed_block,
            derivatives_block, 
            whale_activity_block,
            "______________________________", 
            influencer_final_analysis_block if influencer_final_analysis_block else None, # Добавляем если не пустой
            "______________________________", 
            market_data_block, 
            f"🤖 Анализ и выводы от эксперта GPT на {current_date_str}:",
            main_analytical_text_from_gpt, # Здесь будет уже дедуплицированный текст
            keyword_alert(main_analytical_text_from_gpt), 
            #store_and_compare(main_analytical_text_from_gpt), 
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

        full_report_body_string = "\n\n".join(valid_components)
        data_update_signature = f"---\n📅 Данные на ~ {current_date_str}, обновлены около {update_time_str}."
        final_telegram_message = f"{full_report_body_string}\n\n{data_update_signature}"
        
        log(f"📄 Итоговый отчет собран (длина {len(final_telegram_message)}). Начало: {final_telegram_message[:250].replace(chr(10), ' ')}...")

        # 6. Отправка в Telegram
        if final_telegram_message.strip() and final_telegram_message.strip() != report_title_msg : 
            log(f"📨 Отправка отчета в Telegram (TG_LIMIT_BYTES={TG_LIMIT_BYTES})...")
            send(final_telegram_message, add_numeration_if_multiple_parts=True)
            log("✅ Весь отчёт обработан и отправлен.")
        else:
            log("ℹ️ Итоговый отчет пуст или содержит только заголовок, отправка не требуется.")

        sleep(3) 
        log("🏁 Скрипт завершает работу.")

    except Exception as e: 
        log(f"❌ КРИТИЧЕСКАЯ ОШИБКА В MAIN: {type(e).__name__} - {e}")
        log(traceback.format_exc())
        try:
            if TG_TOKEN and CHANNEL_ID:
                error_message_for_tg = f"📛 КРИТИЧЕСКАЯ ОШИБКА СКРИПТА MomentumPulse:\n{type(e).__name__}: {e}\n\nПроверьте логи для деталей."
                requests.post(
                    f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                    json={"chat_id": CHANNEL_ID, "text": error_message_for_tg[:4090]}, 
                    timeout=10
                )
                log("ℹ️ Уведомление о критической ошибке отправлено в Telegram.")
            else:
                log("⚠️ TG_TOKEN или CHANNEL_ID не установлены, не могу отправить уведомление об ошибке в Telegram.")
        except Exception as tg_err:
            log(f"⚠️ Не удалось отправить уведомление о критической ошибке в Telegram: {tg_err}")
        sys.exit(1)

if __name__ == "__main__":
    main()