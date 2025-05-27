import os
import requests
from datetime import date, datetime, timedelta # datetime, timedelta могут быть не нужны здесь, если yf их не требует
import yfinance as yf

ALPHA_KEY = os.getenv("ALPHA_KEY") # Для get_market_data_text()

# Константы для get_crypto_data
COINGECKO_API_BASE_URL = "https://api.coingecko.com/api/v3"
COINGECKO_HEADERS = {
    'User-Agent': 'DawnMarketPulseBot/1.0 (+https://t.me/DawnMarketPulse)'
}
STABLECOINS_TO_SKIP_ANALYSIS = ["USDT", "USDC"] # Стейблкоины для пропуска в детальном анализе

def format_large_number(num):
    """Форматирует большое число с пробелами в качестве разделителей тысяч."""
    if num is None:
        return "N/A"
    try:
        return f"${int(num):,}".replace(",", " ")
    except (ValueError, TypeError):
        return "N/A"

def get_global_crypto_market_data_text():
    """
    Получает общую капитализацию крипторынка и ее изменение за 24ч.
    """
    try:
        url = f"{COINGECKO_API_BASE_URL}/global"
        r = requests.get(url, timeout=10, headers=COINGECKO_HEADERS)
        r.raise_for_status()
        global_data = r.json().get("data", {})

        total_market_cap = global_data.get("total_market_cap", {}).get("usd", 0)
        market_cap_change_24h = global_data.get("market_cap_change_percentage_24h_usd", 0)

        total_market_cap_formatted = format_large_number(total_market_cap)
        change_formatted = f"{market_cap_change_24h:+.2f}%" if market_cap_change_24h is not None else "N/A"

        return (f"🌍 Общая капитализация крипторынка: {total_market_cap_formatted}\n"
                f"   Изменение за 24ч (глобально): {change_formatted}")
    except requests.exceptions.RequestException as e:
        # print(f"Ошибка при запросе глобальных данных CoinGecko: {e}") # Логирование для отладки
        return "🌍 Не удалось получить данные об общей капитализации крипторынка."
    except Exception as e:
        # print(f"Ошибка при обработке глобальных данных CoinGecko: {e}") # Логирование для отладки
        return "🌍 Ошибка обработки данных об общей капитализации."


def get_crypto_data(extended=False):
    """
    Получает данные по топ-10 криптовалютам с CoinGecko API,
    включая их индивидуальную капитализацию.
    Добавляет краткий анализ (исключая стейблкоины) и сравнение BTC с 7-дневной средней.
    Также добавляет данные об общей капитализации крипторынка.
    """
    final_crypto_block_parts = []

    # 1. Получаем глобальные данные по рынку
    global_market_text = get_global_crypto_market_data_text()
    if global_market_text:
        final_crypto_block_parts.append(global_market_text)

    # 2. Получаем данные по топ-10 криптовалютам
    try:
        today_date_str = date.today().strftime("%d.%m.%Y")
        # Добавляем 'market_cap' в запрос, хотя он обычно и так есть по умолчанию
        coins_url = (
            f"{COINGECKO_API_BASE_URL}/coins/markets"
            "?vs_currency=usd"
            "&order=market_cap_desc"
            "&per_page=10"
            "&page=1"
            "&sparkline=false"
            "&price_change_percentage=24h"
            # "&market_cap=true" # Это не параметр, market_cap уже включен
        )

        r_coins = requests.get(coins_url, timeout=15, headers=COINGECKO_HEADERS)
        r_coins.raise_for_status()
        coins_data = r_coins.json()

        top_coins_lines = [f"\n₿ Крипта на {today_date_str} (Топ-10 по капитализации)"]
        insights = []

        if not coins_data:
            top_coins_lines.append("❌ Не удалось получить данные по топ-10 криптовалютам от CoinGecko.")
        else:
            for coin_data in coins_data:
                symbol = coin_data.get("symbol", "N/A").upper()
                name = coin_data.get("name", "Unknown Coin")
                price = coin_data.get("current_price")
                change_24h = coin_data.get("price_change_percentage_24h")
                market_cap = coin_data.get("market_cap")

                if price is None or change_24h is None:
                    top_coins_lines.append(f"  {symbol}: ❌ неполные данные ({name})")
                    continue

                emoji = "📈" if (change_24h or 0) > 0 else "📉" if (change_24h or 0) < 0 else "📊"

                if 0 < price < 1.0: price_format = f"${price:,.4f}"
                elif price == 0: price_format = "$0.0000"
                else: price_format = f"${price:,.2f}"
                
                market_cap_formatted = f"(кап: {format_large_number(market_cap)})" if market_cap else ""

                top_coins_lines.append(f"  {emoji} <b>{symbol}</b>: {price_format} ({change_24h:+.2f}%) {market_cap_formatted}")

                if extended and symbol not in STABLECOINS_TO_SKIP_ANALYSIS:
                    if abs(change_24h) >= 7:
                        direction = "растёт" if change_24h > 0 else "падает"
                        insights.append(f"— {symbol} ({name}) {direction} более чем на {abs(change_24h):.1f}%. Возможна повышенная волатильность.")
                    elif 0 < abs(change_24h) < 1 and change_24h != 0: # Исключаем строго нулевое изменение
                        insights.append(f"— {symbol} ({name}) почти не изменился ({change_24h:+.2f}%). Возможна консолидация.")
                    # Можно добавить еще условия, если нужно

        if extended and insights:
            top_coins_lines.append("\n→ Краткий анализ по топ криптовалютам (исключая стейблкоины):")
            top_coins_lines.extend(insights)
        elif extended and not insights: # Если extended=True, но инсайтов нет (например, все активные монеты изменились незначительно)
            top_coins_lines.append("\n→ Краткий анализ по топ криптовалютам (исключая стейблкоины):")
            top_coins_lines.append("— Значительных изменений или сигналов для краткого анализа по не-стейблкоинам не выявлено.")


        # Сравнение BTC с 7-дневной средней (эта часть остается)
        try:
            btc_ticker_yf = yf.Ticker("BTC-USD")
            # Запрашиваем на 1 день больше, чтобы иметь 7 предыдущих дней для среднего
            btc_hist = btc_ticker_yf.history(period="8d") # 7 дней для SMA + текущий день

            if not btc_hist.empty and len(btc_hist) >= 2: # Нужны хотя бы 2 записи для текущей цены
                current_price_btc = btc_hist['Close'].iloc[-1]

                if len(btc_hist) >= 8: # 7 предыдущих дней + текущий день
                    # Берем срезы: [-8:-1] означает с 8-го элемента с конца до предпоследнего (7 дней)
                    sma7_btc = btc_hist['Close'].iloc[-8:-1].mean()
                    btc_sma_info_line = f"\n💡 BTC ({format_large_number(current_price_btc).replace('$', '')}) " # Убрал $ для компактности

                    if current_price_btc > sma7_btc:
                        btc_sma_info_line += f"выше своей 7-дневной средней ({format_large_number(sma7_btc).replace('$', '')})."
                    elif current_price_btc < sma7_btc:
                        btc_sma_info_line += f"ниже своей 7-дневной средней ({format_large_number(sma7_btc).replace('$', '')})."
                    else:
                        btc_sma_info_line += f"находится на уровне своей 7-дневной средней ({format_large_number(sma7_btc).replace('$', '')})."
                    top_coins_lines.append(btc_sma_info_line)
                else:
                    top_coins_lines.append(f"\n💡 Недостаточно данных для расчета 7-дневной SMA для BTC (доступно {len(btc_hist)-1} пред. дн.).")
            else:
                top_coins_lines.append("\n💡 Не удалось получить исторические данные для BTC (yfinance) для SMA.")
        except Exception as e_sma:
            # print(f"Ошибка при расчете SMA для BTC: {e_sma}") # Логирование для отладки
            top_coins_lines.append("💡 Не удалось рассчитать 7-дневную среднюю для BTC.")

        final_crypto_block_parts.extend(top_coins_lines)
        return "\n".join(part for part in final_crypto_block_parts if part) # Собираем все части

    except requests.exceptions.HTTPError as http_err:
        error_message = f"Ошибка HTTP при получении данных по криптовалютам CoinGecko: {http_err}"
        # print(error_message) # Логирование для отладки
        final_crypto_block_parts.append(f"\n❌ {error_message}")
        return "\n".join(part for part in final_crypto_block_parts if part)
    except requests.exceptions.Timeout:
        error_message = "Таймаут при запросе данных по криптовалютам от CoinGecko."
        # print(error_message) # Логирование для отладки
        final_crypto_block_parts.append(f"\n❌ {error_message}")
        return "\n".join(part for part in final_crypto_block_parts if part)
    except requests.exceptions.RequestException as req_err:
        error_message = f"Сетевая ошибка при получении данных по криптовалютам CoinGecko: {req_err}"
        # print(error_message) # Логирование для отладки
        final_crypto_block_parts.append(f"\n❌ {error_message}")
        return "\n".join(part for part in final_crypto_block_parts if part)
    except Exception as e:
        error_message = f"Произошла общая ошибка при обработке данных по криптовалютам: {e}"
        # print(error_message) # Логирование для отладки
        final_crypto_block_parts.append(f"\n❌ {error_message}")
        return "\n".join(part for part in final_crypto_block_parts if part)


def get_market_data_text():
    """
    Получает данные по фондовым индексам (ETF через Alpha Vantage, "чистые" индексы через yfinance).
    (Эта функция остается без изменений)
    """
    result_parts = ["📊 Индексы и ETF"]

    # --- ETF через Alpha Vantage ---
    etf_tickers = {
        "S&P 500 ETF (SPY)": "SPY",
        "NASDAQ 100 ETF (QQQ)": "QQQ",
    }
    etf_info_list = []
    if ALPHA_KEY:
        for name, symbol in etf_tickers.items():
            try:
                url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey={ALPHA_KEY}"
                r = requests.get(url, timeout=10)
                r.raise_for_status()
                data = r.json()
                quote = data.get("Global Quote")
                if not quote or "05. price" not in quote or "10. change percent" not in quote:
                    etf_info_list.append(f"  {name}: ❌ ошибка получения данных (AlphaVantage)")
                    continue

                price_str = quote["05. price"]
                change_percent_str = quote["10. change percent"].rstrip('%')

                price = float(price_str)
                change_percent = float(change_percent_str)

                etf_info_list.append(f"  {name}: ${price:,.2f} ({change_percent:+.2f}%)")
            except Exception as e:
                etf_info_list.append(f"  {name}: ❌ ошибка ({e})")
        if etf_info_list:
            result_parts.extend(etf_info_list)
            result_parts.append("    └─ *ETF (Exchange Traded Fund) — это фонд, акции которого торгуются на бирже. Цены ETF отражают стоимость базовых активов фонда, а также включают биржевой спрос/предложение и комиссии.*")
        else: # Если ключ есть, но список пуст (например, из-за ошибок по всем тикерам)
            result_parts.append("  ❌ Не удалось загрузить данные по ETF (AlphaVantage).")
    else:
        result_parts.append("  ℹ️ Alpha Vantage API ключ не настроен, данные по ETF не загружены.")

    # --- "Чистые" индексы через yfinance ---
    index_tickers = {
        "S&P 500 Index (^GSPC)": "^GSPC",
        "NASDAQ Composite Index (^IXIC)": "^IXIC",
        "DAX Index (^GDAXI)": "^GDAXI",
        "Nikkei 225 Index (^N225)": "^N225",
        "FTSE 100 Index (^FTSE)": "^FTSE"
    }
    index_info_list = []
    for name, symbol in index_tickers.items():
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="2d") # Данные за 2 последних торговых дня
            if hist.empty or len(hist) < 2:
                index_info_list.append(f"  {name}: ❌ нет данных (yfinance)")
                continue

            prev_close = hist['Close'].iloc[0]
            current_price = hist['Close'].iloc[-1]

            change = current_price - prev_close
            change_percent = (change / prev_close) * 100

            current_price_formatted = f"{current_price:,.2f} pts"
            index_info_list.append(f"  {name}: {current_price_formatted} ({change_percent:+.2f}%)")
        except Exception as e:
            index_info_list.append(f"  {name}: ❌ ошибка ({e})")

    if index_info_list:
        if etf_info_list and ALPHA_KEY: result_parts.append("") # Добавляем пустую строку для отступа, если оба блока есть
        result_parts.extend(index_info_list)
        result_parts.append("    └─ *Значения индексов выражаются в пунктах и являются «чистыми» статистическими величинами, отражающими совокупную стоимость акций компаний, входящих в индекс.*")
    elif not ALPHA_KEY and not index_info_list : # Если нет ни ETF, ни индексных данных
         result_parts.append("  Не удалось загрузить данные по индексам.")


    if len(result_parts) == 1: # Только заголовок "📊 Индексы и ETF"
         result_parts.append("  Не удалось загрузить данные по индексам и ETF.")

    return "\n".join(result_parts)