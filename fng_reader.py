# fng_reader.py
import requests

def get_fear_and_greed_index_text():
    """
    Получает значение Индекса страха и жадности с alternative.me API.
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
            value = data[0].get("value", "?")
            label = data[0].get("value_classification", "?")
            return f"📊 Индекс страха и жадности: {value} ({label})"
        return "📊 Индекс страха и жадности: данные не найдены."
    except requests.exceptions.RequestException as e:
        return f"📊 Индекс страха и жадности: не удалось получить данные ({type(e).__name__})."
    except Exception as e:
        return f"📊 Индекс страха и жадности: ошибка обработки данных ({type(e).__name__})."
