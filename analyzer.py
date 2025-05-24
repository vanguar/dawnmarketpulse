import re
import os
from datetime import date, timedelta

# Ключевые слова, на которые GPT должен реагировать дополнительно
KEY_TERMS = {
    "AI": "🧠 Упоминание ИИ может указывать на рост интереса к технологиям.",
    "crash": "⚠️ Возможные панические настроения. Стоит быть осторожным.",
    "inflation": "📉 Рост инфляции влияет на макроэкономические решения и ставки.",
    "recession": "📉 Угрозы рецессии могут ослабить фондовые рынки.",
    "interest rates": "💰 Возможное влияние на рынок облигаций и фондовый рынок.",
}

def keyword_alert(text):
    """
    Проверяет текст на наличие ключевых слов и возвращает строку с предупреждениями.
    """
    findings = []
    for word, reaction in KEY_TERMS.items():
        pattern = re.compile(rf"\b{word}\b", re.IGNORECASE)
        if pattern.search(text):
            findings.append(f"• {word}: {reaction}")
    if findings:
        header_text = "⚡️ Обнаружены ключевые сигналы:\n"
        return header_text + "\n".join(findings)
    else:
        return "🟢 Ключевых тревожных сигналов не найдено."

# Примитивный кеш в файл
def store_and_compare(report_text, cache_dir="cache"):
    """
    Сохраняет сегодняшний отчет и сравнивает его с вчерашним, если он есть.
    Возвращает строку с результатом сравнения.
    """
    os.makedirs(cache_dir, exist_ok=True)
    today = date.today().isoformat()
    today_file = os.path.join(cache_dir, f"{today}.txt")

    # Сохраняем сегодняшний отчёт
    with open(today_file, "w", encoding="utf-8") as f:
        f.write(report_text)

    # Пытаемся сравнить с вчерашним
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    yesterday_file = os.path.join(cache_dir, f"{yesterday}.txt")

    if os.path.exists(yesterday_file):
        with open(yesterday_file, "r", encoding="utf-8") as f:
            previous_report_text = f.read()
        # Используем обновленную функцию compare_reports
        return compare_reports(previous_report_text, report_text)
    else:
        return "📊 Данных за вчера нет для сравнения."

def compare_reports(old, new):
    """
    Сравнивает два отчета (старый и новый) и возвращает краткую сводку изменений.
    Эта версия соответствует предложению другой нейросети для большей лаконичности.
    """
    old_lines_set = set(line.strip() for line in old.splitlines() if line.strip())
    new_lines_set = set(line.strip() for line in new.splitlines() if line.strip())

    added_count = len(new_lines_set - old_lines_set)
    removed_count = len(old_lines_set - new_lines_set)

    if added_count == 0 and removed_count == 0:
        return "📊 Изменений в аналитическом блоке GPT по сравнению с прошлым днём не произошло."

    summary = []
    if added_count and removed_count:
        summary.append(f"произошли изменения (~{added_count} добавлено, ~{removed_count} удалено).")
    elif added_count:
        summary.append(f"добавлено ~{added_count} новых строк.")
    elif removed_count: # Исправлено: должно быть removed_count, а не removed_count
        summary.append(f"удалено или изменено ~{removed_count} строк.")
    
    # Если summary остался пустым, но счетчики не нулевые (маловероятно при текущей логике, но для подстраховки)
    if not summary and (added_count > 0 or removed_count > 0):
        return "📊 Аналитический блок GPT был обновлен."
        
    return f"📊 В аналитическом блоке GPT {', '.join(summary)}"