import os
# from fpdf import FPDF # Убрали, так как PDF не нужен
from textblob import TextBlob
from datetime import datetime # Добавили для функции, если будете использовать дату

# Если generate_pdf не используется, ее можно полностью удалить.
# def generate_pdf(text, output_dir="reports"):
#     # ... (код функции)

def get_sentiment_description(polarity, subjectivity):
    """Возвращает текстовое описание полярности и субъективности."""
    
    pol_desc = "нейтральная" # По умолчанию
    if polarity > 0.5:
        pol_desc = "очень позитивная"
    elif polarity > 0.15: # Немного поднял порог для "позитивная"
        pol_desc = "умеренно позитивная"
    elif polarity < -0.5:
        pol_desc = "очень негативная"
    elif polarity < -0.15: # Немного поднял порог для "негативная"
        pol_desc = "умеренно негативная"

    sub_desc = "преимущественно объективный (фокус на фактах)" # По умолчанию
    if subjectivity > 0.75: # Увеличил порог для "очень субъективный"
        sub_desc = "очень субъективный (много личных мнений/эмоций)"
    elif subjectivity > 0.45: # Увеличил порог для "умеренно субъективный"
        sub_desc = "умеренно субъективный (присутствуют личные оценки)"
            
    return f"Тональность текста: {pol_desc}. Стиль изложения: {sub_desc}."


def analyze_sentiment(text):
    """Анализирует тональность текста и возвращает форматированную строку с результатами и расшифровкой."""
    if not isinstance(text, str) or not text.strip():
        return """🧠 Анализ тональности текста GPT:
        • Ошибка: Текст для анализа не предоставлен или пуст."""

    try:
        blob = TextBlob(text)
        polarity = blob.sentiment.polarity
        subjectivity = blob.sentiment.subjectivity

        tone = "📊 Нейтральное" # По умолчанию
        if polarity > 0.15:
            tone = "📈 Позитивное"
        elif polarity < -0.15:
            tone = "📉 Негативное"
        
        sentiment_details_text = get_sentiment_description(polarity, subjectivity)

        return f"""🧠 Анализ тональности текста GPT:
• Настроение (общее): {tone}
• Полярность (от -1 до 1): {polarity:.2f}
• Субъективность (от 0 до 1): {subjectivity:.2f}
• Расшифровка: {sentiment_details_text}"""
    except Exception as e:
        # Логирование ошибки здесь было бы полезно, если бы была передана функция log
        # print(f"Ошибка в analyze_sentiment: {e}") 
        return """🧠 Анализ тональности текста GPT:
        • Ошибка при анализе тональности."""