import os
import requests

def get_market_news():
    try:
        api_key = os.getenv("MARKETAUX_KEY")
        if not api_key:
            print("❗ MARKETAUX_KEY не установлен.")
            return "MARKETAUX API не настроен", False

        url = "https://api.marketaux.com/v1/news/all"
        params = {
            "api_token": api_key,
            "language": "ru,en",
            "countries": "us,gb,de,cn,jp",
            "filter_entities": "true",
            "limit": 5,
            "sort": "published_on",
            "group_similar": "true"
        }

        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        articles = data.get("data", [])

        if not articles:
            return "Реальных новостей по заданным фильтрам не найдено.", False

        result = []
        for article in articles[:3]:
            title = article.get("title", "Без заголовка")
            source = article.get("source", "")
            result.append(f"• {title} ({source})")

        return "\n".join(result), True

    except requests.exceptions.HTTPError as http_err:
        return f"❗ HTTP ошибка при загрузке новостей: {http_err}", False
    except Exception as e:
        return f"❗ Ошибка при загрузке новостей: {e}", False

def get_news_block():
    news_content, has_actual_news = get_market_news()
    if has_actual_news:
        return f"""Новости рынка 📰
{news_content}

→ Пожалуйста, проанализируй эти новости: краткий вывод и возможное влияние.""", True
    else:
        return "", False
