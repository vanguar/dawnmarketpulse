import os
import requests
from datetime import datetime, timedelta

# Список влиятельных лиц. Он будет использоваться в main.py для передачи в GPT.
INFLUENCERS_TO_TRACK = [
    {"id": "elon_musk", "name": "Elon Musk"},
    {"id": "sam_altman", "name": "Sam Altman"},
    {"id": "bill_gates", "name": "Bill Gates"},
    {"id": "jeff_bezos", "name": "Jeff Bezos"},
    {"id": "warren_buffett", "name": "Warren Buffett"},
    {"id": "donald_trump", "name": "Donald Trump"},
    {"id": "a_pompliano", "name": "Anthony Pompliano"},
    {"id": "balaji_s", "name": "Balaji Srinivasan"},
    {"id": "vitalik_buterin", "name": "Vitalik Buterin"},
    {"id": "larry_fink", "name": "Larry Fink"},
    {"id": "cz_binance", "name": "Changpeng Zhao"},
    {"id": "brian_armstrong", "name": "Brian Armstrong"},
    {"id": "cathie_wood", "name": "Cathie Wood"},
    {"id": "michael_saylor", "name": "Michael Saylor"},
    {"id": "jensen_huang", "name": "Jensen Huang"},
    {"id": "jerome_powell", "name": "Jerome Powell"},
    # Добавьте или измените по необходимости
]

def get_market_news():
    """
    Получает основную порцию рыночных новостей (например, топ-5).
    """
    try:
        api_key = os.getenv("MARKETAUX_KEY")
        if not api_key:
            return "MarketAux API ключ не настроен для get_market_news", False

        url = "https://api.marketaux.com/v1/news/all"
        params = {
            "api_token": api_key,
            "language": "ru,en",
            "countries": "us,gb,de,cn,jp,global",
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
            return "Реальных рыночных новостей по заданным фильтрам не найдено.", False

        result = []
        for article in articles[:3]: 
            title = article.get("title", "Без заголовка")
            source = article.get("source", "Неизвестный источник")
            result.append(f"• {title} ({source})")
        return "\n".join(result), True
    except requests.exceptions.HTTPError as http_err:
        return f"❗ HTTP ошибка при загрузке рыночных новостей: {http_err}", False
    except Exception as e:
        return f"❗ Ошибка при загрузке рыночных новостей: {e}", False

def get_news_block():
    """
    Формирует блок основных новостей для GPT.
    """
    news_content, has_actual_news = get_market_news()
    if has_actual_news:
        return f"""Новости рынка 📰
{news_content}

→ Пожалуйста, проанализируй эти новости: краткий вывод и возможное влияние.""", True
    else:
        return "", False


def get_news_pool_for_gpt_analysis():
    """
    Загружает более широкий набор свежих общих новостей (без поиска по ключевым словам),
    который будет использоваться GPT для поиска упоминаний влиятельных лиц.
    Учитывает предложения по улучшению: увеличен limit, изменены countries,
    добавлен filter_entities: false и ослаблена фильтрация по дате.
    """
    api_key = os.getenv("MARKETAUX_KEY")
    if not api_key:
        print("❗ [news_reader] MARKETAUX_KEY не установлен. Невозможно получить пул новостей для анализа GPT.")
        return "🗣️ Ключ MarketAux API не настроен для загрузки пула новостей."

    print("ℹ️ [news_reader] Загрузка расширенного пула новостей для анализа упоминаний GPT (с новыми параметрами)...")
    try:
        url = "https://api.marketaux.com/v1/news/all"
        # Улучшение: Фильтруем новости за последние 2 дня для большего охвата
        published_after_date = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')
        
        params = {
            "api_token": api_key,
            "language": "ru,en",
            "limit": 50,  # Увеличено до 50
            "sort": "published_on",
            "published_after": published_after_date, # Ослаблен фильтр по дате (2 дня)
            "group_similar": "true", 
            "countries": "global",  # Используем только "global" для максимального охвата
            "filter_entities": "false", # Добавлено для получения более "сырых" данных
        }
        # print(f"DEBUG [news_reader] Params for news pool: {params}") # Для отладки параметров
        response = requests.get(url, params=params, timeout=30) # Увеличен таймаут для большего запроса
        response.raise_for_status()
        data = response.json()
        articles = data.get("data", [])

        if not articles:
            print(f"ℹ️ [news_reader] Не найдено статей для формирования пула новостей для GPT (за последние 2 дня, limit 50, countries: global, filter_entities: false).")
            return "🗣️ Не удалось загрузить пул общих новостей для поиска упоминаний влиятельных лиц (возможно, нет свежих новостей по критериям)."

        news_texts = []
        for i, article in enumerate(articles):
            title = article.get("title", "Без заголовка").strip()
            snippet = article.get("snippet", "").strip()
            description = article.get("description", "").strip()
            
            content_for_gpt = snippet
            if not content_for_gpt and description:
                content_for_gpt = description
            elif not content_for_gpt:
                content_for_gpt = "Содержание отсутствует." # Если и то, и другое пустое
            
            # Ограничиваем длину контента для каждой новости, чтобы не перегружать GPT
            max_content_len = 500 # Символов на новость (сниппет + описание)
            content_for_gpt = content_for_gpt[:max_content_len] + ('...' if len(content_for_gpt) > max_content_len else '')

            article_text = f"Новость {i+1}: {title}\nСодержание: {content_for_gpt}"
            news_texts.append(article_text)
        
        print(f"ℹ️ [news_reader] Загружено {len(articles)} статей в пул для GPT (параметры: limit 50, published_after: {published_after_date}, countries: global, filter_entities: false).")
        return "\n\n---\n\n".join(news_texts)

    except requests.exceptions.HTTPError as http_err:
        error_details = ""
        if http_err.response is not None:
            error_details = f" - Status: {http_err.response.status_code}, Response: {http_err.response.text[:200]}"
        print(f"❗ [news_reader] HTTP ошибка MarketAux при загрузке пула новостей: {http_err}{error_details}")
        return f"🗣️ Ошибка при загрузке пула новостей (HTTP): {http_err.response.status_code if http_err.response is not None else 'Unknown'}"
    except requests.exceptions.RequestException as req_err:
        print(f"❗ [news_reader] Ошибка сети при загрузке пула новостей: {req_err}")
        return f"🗣️ Ошибка сети при загрузке пула новостей."
    except Exception as e:
        print(f"❗ [news_reader] Непредвиденная ошибка при загрузке пула новостей: {e}")
        return f"🗣️ Непредвиденная ошибка при загрузке пула новостей."