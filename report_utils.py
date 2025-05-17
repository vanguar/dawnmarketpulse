from fpdf import FPDF
import os

def generate_pdf(text, filename="report.pdf"):
    pdf = FPDF()
    pdf.add_page()

    # Добавляем шрифт с поддержкой Unicode
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    if not os.path.isfile(font_path):
        raise FileNotFoundError(f"Не найден шрифт для Unicode: {font_path}")

    pdf.add_font("DejaVu", "", font_path, uni=True)
    pdf.set_font("DejaVu", size=12)

    # Добавляем строки текста
    for line in text.split("\n"):
        pdf.multi_cell(0, 10, line)

    pdf.output(filename)
    return filename

def analyze_sentiment(text):
    # Простейший заглушка-анализ
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

