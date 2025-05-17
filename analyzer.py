import re
import os
from datetime import date

# Ключевые слова, на которые GPT должен реагировать дополнительно
KEY_TERMS = {
    "AI": "🧠 Упоминание ИИ может указывать на рост интереса к технологиям.",
    "crash": "⚠️ Возможные панические настроения. Стоит быть осторожным.",
    "inflation": "📉 Рост инфляции влияет на макроэкономические решения и ставки.",
    "recession": "📉 Угрозы рецессии могут ослабить фондовые рынки.",
    "interest rates": "💰 Возможное влияние на рынок облигаций и фондовый рынок.",
}

def keyword_alert(text):
    findings = []
    for word, reaction in KEY_TERMS.items():
        pattern = re.compile(rf"\b{word}\b", re.IGNORECASE)
        if pattern.search(text):
            findings.append(f"• {word}: {reaction}")
    if findings:
        return '🔺 Обнаружены ключевые сигналы:\n' + "\n".join(findings)
" + "\n".join(findings)
    else:
        return "🟢 Ключевых тревожных сигналов не найдено."

# Примитивный кеш в файл
def store_and_compare(report_text, cache_dir="cache"):
    os.makedirs(cache_dir, exist_ok=True)
    today = date.today().isoformat()
    today_file = os.path.join(cache_dir, f"{today}.txt")

    # Сохраняем сегодняшний отчёт
    with open(today_file, "w", encoding="utf-8") as f:
        f.write(report_text)

    # Пытаемся сравнить с вчерашним
    from datetime import timedelta
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    yesterday_file = os.path.join(cache_dir, f"{yesterday}.txt")

    if os.path.exists(yesterday_file):
        with open(yesterday_file, "r", encoding="utf-8") as f:
            previous = f.read()
        return f"📊 Сравнение с вчерашним отчётом:
{compare_reports(previous, report_text)}"
    else:
        return "📊 Данных за вчера нет для сравнения."

def compare_reports(old, new):
    old_lines = set(old.splitlines())
    new_lines = set(new.splitlines())
    added = new_lines - old_lines
    removed = old_lines - new_lines
    result = []
    if added:
        result.append("➕ Новые строки:")
        result.extend(["  " + line for line in added])
    if removed:
        result.append("➖ Удалено:")
        result.extend(["  " + line for line in removed])
    return "\n".join(result) if result else "Изменений нет."
