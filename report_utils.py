def analyze_sentiment(text):
    # Простейший анализатор
    positive_words = ["рост", "успех", "рекорд", "прибыль"]
    negative_words = ["падение", "убыток", "кризис", "обвал"]

    pos = sum(word in text.lower() for word in positive_words)
    neg = sum(word in text.lower() for word in negative_words)

    if pos > neg:
        return "📈 Общий тон отчёта: положительный."
    elif neg > pos:
        return "📉 Общий тон отчёта: негативный."
    else:
        return "⚖️ Общий тон отчёта: нейтральный."
