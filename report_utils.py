import os
from datetime import datetime
#from fpdf import FPDF
from textblob import TextBlob

def generate_pdf(text, output_dir="reports"):
    os.makedirs(output_dir, exist_ok=True)
    today = datetime.today().strftime("%Y-%m-%d")
    filename = os.path.join(output_dir, f"report_{today}.pdf")

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    for line in text.splitlines():
        pdf.multi_cell(0, 10, line)

    pdf.output(filename)
    return filename

def analyze_sentiment(text):
    blob = TextBlob(text)
    polarity = blob.sentiment.polarity
    subjectivity = blob.sentiment.subjectivity

    if polarity > 0.2:
        tone = "📈 Оптимистичный"
    elif polarity < -0.2:
        tone = "📉 Негативный"
    else:
        tone = "📊 Нейтральный"

    return f"""🧠 Анализ тональности:
• Настроение: {tone}
• Полярность: {polarity:.2f}
• Субъективность: {subjectivity:.2f}
"""
