import os
import requests
from datetime import date, datetime, timedelta
import yfinance as yf # Импортируем yfinance

ALPHA_KEY = os.getenv("ALPHA_KEY")

def get_crypto_data(extended=False):
    """
    Получает данные по топ-10 криптовалютам с CoinGecko API,
    добавляет краткий анализ и сравнение BTC с 7-дневной средней.
    """
    try:
        today_date_str = date.today().strftime("%d.%m.%Y")
        
        # Запрашиваем топ-10 криптовалют по рыночной капитализации
        url = (
            "https://api.coingecko.com/api/v3/coins/markets"
            "?vs_currency=usd"
            "&order=market_cap_desc"
            "&per_page=10"  # Получаем топ-10
            "&page=1"
            "&sparkline=false" # Графики не нужны
            "&price_change_percentage=24h" # Убедимся, что изменение за 24ч включено
        )
        
        # ДОБАВЛЯЕМ ЗАГОЛОВОК USER-AGENT
        # Замените на реальный URL вашего проекта или контакт, если есть, или оставьте общим
        headers = {
            'User-Agent': 'DawnMarketPulseBot/1.0 (+ваш-телеграм-канал-или-контакт)'
        }
        
        # Используем увеличенный таймаут и добавленный User-Agent
        r = requests.get(url, timeout=15, headers=headers)
        r.raise_for_status() # Проверка на HTTP ошибки (4xx, 5xx)
        data = r.json()

        result_lines = [f"₿ Крипта на {today_date_str} (Топ-10 по капитализации)"]
        insights = [] # Для расширенного анализа, если extended=True

        if not data: # Если API вернул пустой список
            result_lines.append("❌ Не удалось получить данные по криптовалютам от CoinGecko.")
            return "\n".join(result_lines)

        for coin_data in data:
            # Получаем основные данные по монете
            symbol = coin_data.get("symbol", "N/A").upper() # Тикер, например "BTC"
            name = coin_data.get("name", "Unknown Coin")    # Полное имя, например "Bitcoin"
            price = coin_data.get("current_price")
            change_24h = coin_data.get("price_change_percentage_24h")

            # Проверка на полноту данных
            if price is None or change_24h is None:
                result_lines.append(f"{symbol}: ❌ неполные данные ({name})")
                continue

            # Определяем эмодзи для тренда
            emoji = "📈" if change_24h > 0 else "📉" if change_24h < 0 else "📊"

            # Форматирование цены в зависимости от ее величины
            if 0 < price < 1.0:
                price_format = f"${price:,.4f}" # 4 знака после запятой для цен меньше $1
            elif price == 0:
                price_format = "$0.0000" # Или просто "$0" на ваше усмотрение
            else:
                price_format = f"${price:,.2f}" # 2 знака для цен больше или равных $1

            result_lines.append(f"{emoji} {symbol}: {price_format} ({change_24h:+.2f}%)")

            # Дополнительный анализ, если запрошено
            if extended:
                if abs(change_24h) >= 7: # Порог для "значительного" изменения можно настроить
                    direction = "растёт" if change_24h > 0 else "падает"
                    insights.append(f"— {symbol} ({name}) {direction} более чем на {abs(change_24h):.1f}%. Возможна повышенная волатильность.")
                # Можно добавить другие условия для инсайтов, например, для монет с очень малым изменением
                elif 0 < abs(change_24h) < 1:
                     insights.append(f"— {symbol} ({name}) почти не изменился ({change_24h:+.2f}%). Возможна консолидация.")


        if extended and insights:
            result_lines.append("\n→ Краткий анализ по топ криптовалютам:")
            result_lines.extend(insights)
        
        # Дополнительно: сравнение BTC с 7-дневной средней (SMA7)
        # Этот блок можно вынести в отдельную функцию, если он станет сложнее
        try:
            btc_ticker_yf = yf.Ticker("BTC-USD")
            # Запрашиваем данные за последние 8 дней, чтобы иметь 7 полных дней для среднего + текущий день
            btc_hist = btc_ticker_yf.history(period="8d") 
            
            if not btc_hist.empty and len(btc_hist) >= 2: # Нужно хотя бы 2 точки для сравнения и расчета SMA
                # Последняя доступная цена закрытия (обычно это цена закрытия предыдущего дня UTC для yfinance)
                current_price_btc = btc_hist['Close'].iloc[-1] 
                
                # Расчет 7-дневной скользящей средней по ценам закрытия
                # Берем цены закрытия за 7 дней, предшествующих последней доступной цене
                if len(btc_hist) >= 8: # Убедимся, что достаточно данных для SMA7
                    sma7_btc = btc_hist['Close'].iloc[-8:-1].mean() # Среднее за 7 дней до последнего дня
                    
                    btc_sma_info_line = f"\n💡 BTC (${current_price_btc:,.2f}) "
                    if current_price_btc > sma7_btc:
                        btc_sma_info_line += f"выше своей 7-дневной средней (${sma7_btc:,.2f})."
                    elif current_price_btc < sma7_btc:
                        btc_sma_info_line += f"ниже своей 7-дневной средней (${sma7_btc:,.2f})."
                    else:
                        btc_sma_info_line += f"находится на уровне своей 7-дневной средней (${sma7_btc:,.2f})."
                    result_lines.append(btc_sma_info_line)
                else:
                    result_lines.append(f"\n💡 Недостаточно данных для расчета 7-дневной SMA для BTC ({len(btc_hist)} дн.).")
            else:
                result_lines.append("\n💡 Не удалось получить исторические данные для BTC (yfinance).")
        except Exception as e:
            # Логирование ошибки здесь было бы полезно, если бы была передана функция log из main.py
            # print(f"DEBUG: Ошибка при расчете SMA для BTC: {e}") # для локальной отладки
            result_lines.append(f"\n💡 Не удалось рассчитать 7-дневную среднюю для BTC (ошибка: {e}).")

        return "\n".join(result_lines)

    except requests.exceptions.HTTPError as http_err:
        # Обработка HTTP ошибок (например, 401, 403, 404, 429, 5xx)
        return f"₿ Ошибка HTTP при получении данных по криптовалютам: {http_err}"
    except requests.exceptions.Timeout:
        return "₿ Таймаут при запросе данных по криптовалютам от CoinGecko."
    except requests.exceptions.RequestException as req_err:
        # Другие сетевые ошибки (например, проблемы с DNS)
        return f"₿ Сетевая ошибка при получении данных по криптовалютам: {req_err}"
    except Exception as e:
        # Любые другие непредвиденные ошибки
        # В идеале, здесь тоже нужно логирование traceback для отладки
        # import traceback
        # print(traceback.format_exc()) # для локальной отладки
        return f"₿ Произошла ошибка при получении данных по криптовалютам: {e}"


def get_market_data_text():
    """
    Получает данные по фондовым индексам (ETF через Alpha Vantage, "чистые" индексы через yfinance).
    """
    result_parts = ["📊 Индексы и ETF"]

    # --- ETF через Alpha Vantage ---
    etf_tickers = {
        "S&P 500 ETF (SPY)": "SPY",
        "NASDAQ 100 ETF (QQQ)": "QQQ",
        # "MSCI Japan ETF (EWJ)": "EWJ" # ETF на Японию, если нужен
    }
    etf_info_list = []
    if ALPHA_KEY: # Продолжаем использовать Alpha Vantage, если ключ есть
        for name, symbol in etf_tickers.items():
            try:
                url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey={ALPHA_KEY}"
                r = requests.get(url, timeout=10)
                r.raise_for_status()
                data = r.json()
                quote = data.get("Global Quote")
                if not quote or "05. price" not in quote or "10. change percent" not in quote:
                    etf_info_list.append(f"{name}: ❌ ошибка получения данных (AlphaVantage)")
                    continue

                price_str = quote["05. price"]
                change_percent_str = quote["10. change percent"].rstrip('%')

                price = float(price_str)
                change_percent = float(change_percent_str)

                etf_info_list.append(f"{name}: ${price:,.2f} ({change_percent:+.2f}%)")
            except Exception as e:
                etf_info_list.append(f"{name}: ❌ ошибка ({e})")
        if etf_info_list:
            result_parts.extend(etf_info_list)
            result_parts.append("   └─ *ETF (Exchange Traded Fund) — это фонд, акции которого торгуются на бирже. Цены ETF отражают стоимость базовых активов фонда, а также включают биржевой спрос/предложение и комиссии.*")

    else:
        result_parts.append("Alpha Vantage API ключ не настроен, данные по ETF не загружены.")

    # --- "Чистые" индексы через yfinance ---
    index_tickers = {
        "S&P 500 Index (^GSPC)": "^GSPC",
        "NASDAQ Composite Index (^IXIC)": "^IXIC",
        "DAX Index (^GDAXI)": "^GDAXI", # Тикер DAX для Yahoo Finance
        "Nikkei 225 Index (^N225)": "^N225",
        "FTSE 100 Index (^FTSE)": "^FTSE"
    }
    index_info_list = []
    for name, symbol in index_tickers.items():
        try:
            ticker = yf.Ticker(symbol)
            # Получаем данные за последние 2 торговых дня, чтобы рассчитать изменение
            hist = ticker.history(period="2d")
            if hist.empty or len(hist) < 2:
                index_info_list.append(f"{name}: ❌ нет данных (yfinance)")
                continue

            prev_close = hist['Close'].iloc[0]
            current_price = hist['Close'].iloc[-1] # Последняя цена закрытия

            change = current_price - prev_close
            change_percent = (change / prev_close) * 100

            # Округляем для вывода (пример, можно настроить)
            current_price_formatted = f"{current_price:,.2f} pts"
            index_info_list.append(f"{name}: {current_price_formatted} ({change_percent:+.2f}%)")
        except Exception as e:
            index_info_list.append(f"{name}: ❌ ошибка ({e})")

    if index_info_list:
        if etf_info_list and index_info_list : result_parts.append("") # Добавляем пустую строку для отступа, если оба блока есть
        result_parts.extend(index_info_list)
        result_parts.append("   └─ *Значения индексов выражаются в пунктах и являются «чистыми» статистическими величинами, отражающими совокупную стоимость акций компаний, входящих в индекс.*")


    # Формируем итоговый блок
    if not etf_info_list and not index_info_list:
         result_parts.append("Не удалось загрузить данные по индексам и ETF.")

    return "\n".join(result_parts)