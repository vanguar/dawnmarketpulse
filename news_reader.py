import os
import requests

def get_market_news():
    try:
        api_key = os.getenv("MARKETAUX_KEY")
        url = "https://api.marketaux.com/v1/news/all"
        params = {
            "api_token": api_key,
            "language": "en",
            "limit": 3,
            "published_after": "1 day ago",
            "filter_entities": "true"
        }
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        articles = data.get("data", [])
        result = []
        for article in articles:
            title = article.get("title", "Без заголовка")
            source = article.get("source", {}).get("name", "")
            result.append(f"• {title} ({source})")
        if not result:
            return "Нет свежих новостей."
        return "\n".join(result)
    except Exception as e:
        return f"❗ Ошибка загрузки новостей: {e}"

def get_news_block():
    news = get_market_news()
    return f"""Новости рынка 📰
{news}

→ Краткий вывод GPT по новостям: на что стоит обратить внимание?
"""
