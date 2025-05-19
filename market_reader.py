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

        url = (
            "https://api.coingecko.com/api/v3/coins/markets"
            "?vs_currency=usd"
            "&order=market_cap_desc"
            "&per_page=10"
            "&page=1"
            "&sparkline=false"
            "&price_change_percentage=24h"
        )

        headers = {
            'User-Agent': 'DawnMarketPulseBot/1.0 (+https://t.me/DawnMarketPulse)'
        }

        r = requests.get(url, timeout=15, headers=headers)
        r.raise_for_status()
        data = r.json()

        result_lines = [f"₿ Крипта на {today_date_str} (Топ-10 по капитализации)"]
        insights = []

        if not data:
            result_lines.append("❌ Не удалось получить данные по криптовалютам от CoinGecko.")
            return "\n".join(result_lines)

        for coin_data in data:
            symbol = coin_data.get("symbol", "N/A").upper()
            name = coin_data.get("name", "Unknown Coin")
            price = coin_data.get("current_price")
            change_24h = coin_data.get("price_change_percentage_24h")

            if price is None or change_24h is None:
                result_lines.append(f"{symbol}: ❌ неполные данные ({name})")
                continue

            emoji = "📈" if change_24h > 0 else "📉" if change_24h < 0 else "📊"

            if 0 < price < 1.0:
                price_format = f"${price:,.4f}"
            elif price == 0:
                price_format = "$0.0000"
            else:
                price_format = f"${price:,.2f}"

            result_lines.append(f"{emoji} {symbol}: {price_format} ({change_24h:+.2f}%)")

            if extended:
                if abs(change_24h) >= 7:
                    direction = "растёт" if change_24h > 0 else "падает"
                    insights.append(f"— {symbol} ({name}) {direction} более чем на {abs(change_24h):.1f}%. Возможна повышенная волатильность.")
                elif 0 < abs(change_24h) < 1:
                    insights.append(f"— {symbol} ({name}) почти не изменился ({change_24h:+.2f}%). Возможна консолидация.")

        if extended and insights:
            result_lines.append("\n→ Краткий анализ по топ криптовалютам:")
            result_lines.extend(insights)

        # Сравнение BTC с 7-дневной средней
        try:
            btc_ticker_yf = yf.Ticker("BTC-USD")
            btc_hist = btc_ticker_yf.history(period="8d")

            if not btc_hist.empty and len(btc_hist) >= 2:
                current_price_btc = btc_hist['Close'].iloc[-1]

                if len(btc_hist) >= 8:
                    sma7_btc = btc_hist['Close'].iloc[-8:-1].mean()
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
        except Exception as e_sma:
            result_lines.append("💡 Не удалось рассчитать 7-дневную среднюю для BTC. Подробнее: " + repr(e_sma))

        return "\n".join(result_lines)

    except requests.exceptions.HTTPError as http_err:
        return "Ошибка HTTP при получении данных по криптовалютам. Подробнее: " + repr(http_err)
    except requests.exceptions.Timeout:
        return "Таймаут при запросе данных по криптовалютам от CoinGecko."
    except requests.exceptions.RequestException as req_err:
        return "Сетевая ошибка при получении данных по криптовалютам. Подробнее: " + repr(req_err)
    except Exception as e:
        return "Произошла ошибка при получении данных по криптовалютам. Подробнее: " + repr(e)



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