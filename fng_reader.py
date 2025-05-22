# fng_reader.py
import requests

def get_fear_and_greed_index_text():
    """
    Получает значение Индекса страха и жадности с alternative.me API и добавляет пояснение.
    Если данные не получены — возвращает пустую строку.
    """
    try:
        url = "https://api.alternative.me/fng/?limit=1"
        headers = {
            'User-Agent': 'MomentumPulseBot/1.0 (+https://t.me/MomentumPulse)'
        }
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json().get("data", [])
        if data:
            value = int(data[0].get("value", "0"))
            label = data[0].get("value_classification", "Unknown")

            explanation = {
                "Extreme Fear": "инвесторы паникуют, возможны хорошие точки входа",
                "Fear": "рынок насторожен, возможна коррекция",
                "Neutral": "настроения сбалансированы",
                "Greed": "инвесторы активны, но возможна перекупленность",
                "Extreme Greed": "рынок перегрет — велика вероятность коррекции"
            }.get(label, "настроения неопределённые")

            if value <= 25:
                emoji = "🔴"
            elif value <= 50:
                emoji = "🟡"
            else:
                emoji = "🟢"

            return f"{emoji} Индекс страха и жадности: {value} ({label}) — {explanation}."
        else:
            return ""  # ничего не выводим при отсутствии данных
    except Exception:
        return ""  # ничего не выводим при ошибке
