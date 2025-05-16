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
TG_TOKEN = os.getenv("TG_TOKEN")  # Убран лишний пробел
CHAT_ID = os.getenv("CHANNEL_ID")  # Убраны лишние пробелы, возвращено CHANNEL_ID для единообразия, если хотите CHAT_ID - оставьте

MODEL = "gpt-4o-mini"  # при желании gpt-4o
TIMEOUT = 60
GPT_TOKENS = 450  # ≈ 1 700-1 900 симв.
TG_LIMIT = 4096  # лимит Telegram
CUT_LEN = 3500  # запас от лимита (эффективная длина для wrap будет CUT_LEN - 50)

# ── PROMPT ──────────────────────────────────────────────────────
PROMPT = """
🗓️ **Утренний обзор • {date}** ☀️

---

📊 **Ситуация на рынках:**

* **Индексы** (S&P 500, DAX, Nikkei, Nasdaq fut):
    * _Основные движения и показатели._
    * ➡️ _Что это значит для инвестора? Краткий анализ._

---

🚀 **Акции: Взлеты и Падения** 📉

* **Лидеры роста** (2-3 бумаги):
    * _Название компании (тикер): причина роста (новость, отчет, и т.д.)._
* **Аутсайдеры** (2-3 бумаги):
    * _Название компании (тикер): причина падения._
* ➡️ _Общий вывод по динамике акций._

---

₿ **Криптовалюты: Обзор** 💎

* **Основные монеты** (BTC, ETH):
    * _Динамика, ключевые уровни._
* **Интересные альткоины** (до 3):
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
‼️ **Важно:** Ответ должен быть только обычным текстом. Эмодзи активно приветствуются для наглядности. HTML/Markdown не использовать. Максимум ~1600 символов для всего ответа.
"""

TG_URL = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"

# ── helpers ─────────────────────────────────────────────────────
def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S %Z}] {msg}", flush=True) # Добавил %Z для таймзоны

def gpt_report() -> str:
    try:
        resp = openai.ChatCompletion.create(
            model=MODEL,
            messages=[{"role": "user", "content": PROMPT.format(date=date.today().strftime("%d.%m.%Y"))}], # Добавил форматирование даты
            timeout=TIMEOUT,
            temperature=0.4, # Можно немного увеличить для разнообразия (0.5-0.7), если ответы слишком сухие
            max_tokens=GPT_TOKENS,
        )
        return resp.choices[0].message.content.strip()
    except openai.error.OpenAIError as e: # Более специфичный обработчик ошибок OpenAI
        log(f"OpenAI API Error: {e}")
        raise # Пробрасываем ошибку выше, чтобы main мог ее обработать
    except Exception as e:
        log(f"Error in gpt_report: {e}")
        raise

def chunk(text: str, size: int = CUT_LEN):
    # Запас 50 символов от выбранного CUT_LEN.
    # Эффективная ширина для textwrap будет size - 50 - длина префикса (макс ~10 для "(10/10)\n")
    # Реальный запас для текста будет около 60+ символов.
    effective_width = size - 50 - 10 # Дополнительный небольшой запас для префикса
    parts = wrap(text, width=effective_width,
                 break_long_words=False,
                 replace_whitespace=False, # Чтобы сохранить переносы строк, если они есть от GPT
                 drop_whitespace=True,
                 break_on_hyphens=False)
    total = len(parts)
    if total == 0: # Если текст пустой или только пробелы после strip
        return [""] # Возвращаем одну пустую строку, чтобы избежать ошибок в цикле
    if total == 1:
        return parts
    return [f"({i+1}/{total})\n{p.strip()}" for i, p in enumerate(parts) if p.strip()] # Убираем пустые части, если wrap их создал

def send(part: str):
    if not part: # Не отправлять пустые сообщения
        log("Attempted to send an empty part. Skipping.")
        return

    json_payload = {
        "chat_id": CHAT_ID,
        "text": part,
        "disable_web_page_preview": True
        # "parse_mode": "MarkdownV2" # или "HTML" если решите использовать, но тогда PROMPT нужно менять
    }
    try:
        r = requests.post(TG_URL, json=json_payload, timeout=10)
        r.raise_for_status() # Проверка на HTTP ошибки (4xx, 5xx)
        log(f"Part sent successfully to {CHAT_ID}.")
    except requests.exceptions.HTTPError as e:
        log(f"TG HTTP Error {r.status_code} for {CHAT_ID}: {r.text}. Error: {e}")
    except requests.exceptions.RequestException as e:
        log(f"TG Request Error for {CHAT_ID}: {e}")
    except Exception as e:
        log(f"Generic error in send function for {CHAT_ID}: {e}")


# ── main ────────────────────────────────────────────────────────
def main():
    log("Script started. Attempting to generate and send report...")
    try:
        report_text = gpt_report()
        if not report_text or report_text.isspace():
            log("GPT returned an empty or whitespace-only report. Exiting.")
            return

        segments = chunk(report_text)
        if not segments or not any(s.strip() for s in segments): # Проверка, что есть непустые сегменты
            log("Chunking resulted in no valid segments. Exiting.")
            return

        log(f"Report chunked into {len(segments)} segment(s).")

        for i, seg in enumerate(segments):
            log(f"Sending segment {i+1}/{len(segments)}...")
            send(seg)
            if i < len(segments) - 1: # Пауза не нужна после последнего сегмента
                sleep(1.5)  # Немного увеличил паузу для надежности
        log("All segments processed. Posted OK.")
    except openai.error.OpenAIError as e: # Ловим ошибки API OpenAI отдельно
        log(f"Fatal OpenAI API Error: {e}")
        sys.exit(1)
    except requests.exceptions.RequestException as e: # Ловим ошибки сети при отправке
        log(f"Fatal Telegram API Request Error: {e}")
        sys.exit(1)
    except Exception as e:
        log(f"Fatal error in main execution: {e}")
        import traceback
        log(f"Traceback: {traceback.format_exc()}") # Более детальный трейсбек для отладки
        sys.exit(1)

if __name__ == "__main__":
    main()

