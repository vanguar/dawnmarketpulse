# market_reader.py
import os
import requests
from datetime import date
import yfinance as yf

ALPHA_KEY = os.getenv("ALPHA_KEY") # Для get_market_data_text()

# Константы для CoinGecko
COINGECKO_API_BASE_URL = "https://api.coingecko.com/api/v3"
COINGECKO_HEADERS = {
    'User-Agent': 'MomentumPulseBot/1.0 (+https://t.me/MomentumPulse)' # Обновлено
}

# Константы для CoinMarketCap
COINMARKETCAP_API_KEY = os.getenv("COINMARKETCAP_KEY")
COINMARKETCAP_API_BASE_URL = "https://pro-api.coinmarketcap.com/v1"
CMC_HEADERS = {
    'Accepts': 'application/json',
    'X-CMC_PRO_API_KEY': COINMARKETCAP_API_KEY,
    'User-Agent': 'MomentumPulseBot/1.0 (+https://t.me/MomentumPulse)' # Обновлено
}

STABLECOINS_TO_SKIP_ANALYSIS = ["USDT", "USDC", "DAI", "TUSD", "BUSD", "USDP"]

def format_large_number(num):
    """Форматирует большое число с пробелами в качестве разделителей тысяч."""
    if num is None:
        return "N/A"
    try:
        if isinstance(num, (float, int)):
            return f"${num:,.0f}".replace(",", " ")
        return f"${int(num):,}".replace(",", " ")
    except (ValueError, TypeError):
        return "N/A"

def _fetch_crypto_data_cmc(limit=10):
    """
    Вспомогательная функция для получения данных топ-N криптовалют с CoinMarketCap.
    Возвращает (данные_монет, общая_капитализация, изменение_капитализации_24ч, сообщение_об_ошибке).
    """
    if not COINMARKETCAP_API_KEY:
        return None, None, None, "CoinMarketCap API ключ не настроен."

    coins_data_cmc_transformed = []
    total_market_cap_usd = None
    market_cap_global_change_24h_cmc = None

    try:
        # 1. Глобальные метрики
        global_url = f"{COINMARKETCAP_API_BASE_URL}/global-metrics/quotes/latest"
        r_global = requests.get(global_url, headers=CMC_HEADERS, timeout=10)
        r_global.raise_for_status()
        response_json_global = r_global.json()
        global_data_cmc = response_json_global.get("data", {})

        outer_quote_obj = global_data_cmc.get("quote", {})
        if not isinstance(outer_quote_obj, dict):
            print(f"ERROR: CMC Global Metrics - 'data.quote' is not a dictionary: {outer_quote_obj}") # ЗАМЕНИТЬ НА log()
            return None, None, None, "Некорректная структура ответа от CMC для Global Metrics (data.quote)."

        inner_quote_obj = outer_quote_obj.get("quote", {})
        if not isinstance(inner_quote_obj, dict):
            print(f"ERROR: CMC Global Metrics - 'data.quote.quote' is not a dictionary: {inner_quote_obj}") # ЗАМЕНИТЬ НА log()
            return None, None, None, "Некорректная структура ответа от CMC для Global Metrics (data.quote.quote)."

        quote_usd_global = inner_quote_obj.get("USD", {})
        if not isinstance(quote_usd_global, dict):
            print(f"ERROR: CMC Global Metrics - 'data.quote.quote.USD' is not a dictionary: {quote_usd_global}") # ЗАМЕНИТЬ НА log()
            return None, None, None, "Некорректная структура ответа от CMC для Global Metrics (data.quote.quote.USD)."

        total_market_cap_usd = quote_usd_global.get("total_market_cap")
        market_cap_global_change_24h_cmc = quote_usd_global.get("total_market_cap_yesterday_percentage_change")

        if total_market_cap_usd is None:
            print("WARNING: CMC Global Metrics - 'total_market_cap' is None.") # ЗАМЕНИТЬ НА log()
        if market_cap_global_change_24h_cmc is None:
            print("WARNING: CMC Global Metrics - 'total_market_cap_yesterday_percentage_change' is None.") # ЗАМЕНИТЬ НА log()

        # 2. Топ N монет
        listings_url = f"{COINMARKETCAP_API_BASE_URL}/cryptocurrency/listings/latest"
        parameters = {
            'start': '1',
            'limit': str(limit),
            'convert': 'USD',
            'sort': 'market_cap'
        }
        r_coins = requests.get(listings_url, headers=CMC_HEADERS, params=parameters, timeout=15)
        r_coins.raise_for_status()
        raw_coins_data = r_coins.json().get("data", []) # Ожидаем список здесь

        if not isinstance(raw_coins_data, list): # Доп. проверка, что это список
            print(f"ERROR: CMC Listings - 'data' is not a list: {raw_coins_data}") # ЗАМЕНИТЬ НА log()
            return coins_data_cmc_transformed, total_market_cap_usd, market_cap_global_change_24h_cmc, "Некорректный формат ответа от CMC для Listings (ожидался список)."


        if not raw_coins_data: # Если список пуст
            # Это не обязательно ошибка, API мог вернуть 0 результатов по запросу
            print("INFO: CMC Listings - received an empty list of coins.") # ЗАМЕНИТЬ НА log()
            # Возвращаем то, что есть по глобальным данным, и пустой список монет
            return [], total_market_cap_usd, market_cap_global_change_24h_cmc, None


        for coin_entry in raw_coins_data: # coin_entry это объект монеты из списка
            quote_data = coin_entry.get("quote", {})
            quote_usd_coin = quote_data.get("USD", {}) # Доступ к USD данным внутри quote

            coins_data_cmc_transformed.append({
                "symbol": coin_entry.get("symbol", "N/A").upper(),
                "name": coin_entry.get("name", "Unknown Coin"),
                "current_price": quote_usd_coin.get("price"),
                "price_change_percentage_24h": quote_usd_coin.get("percent_change_24h"),
                "market_cap": quote_usd_coin.get("market_cap"),
            })
        
        return coins_data_cmc_transformed, total_market_cap_usd, market_cap_global_change_24h_cmc, None

    except requests.exceptions.HTTPError as http_err:
        error_message_detail = str(http_err)
        try:
            error_content = http_err.response.json()
            error_message_detail = error_content.get("status", {}).get("error_message", str(http_err))
        except: pass
        error_message = f"Ошибка HTTP CoinMarketCap: {http_err.response.status_code if http_err.response else 'Unknown'} ({error_message_detail})"
        return None, None, None, error_message
    except requests.exceptions.RequestException as e:
        return None, None, None, f"Сетевая ошибка CoinMarketCap: {e}"
    except Exception as e: # Ловим более общие исключения в конце
        print(f"CRITICAL: Unexpected error in _fetch_crypto_data_cmc: {e}") # ЗАМЕНИТЬ НА log()
        # import traceback # Раскомментировать для детального трейсбека в логах
        # print(traceback.format_exc()) # ЗАМЕНИТЬ НА log()
        return None, None, None, f"Общая непредвиденная ошибка CoinMarketCap: {type(e).__name__}"


def _fetch_crypto_data_coingecko(limit=10):
    """
    Вспомогательная функция для получения данных топ-N криптовалют с CoinGecko.
    Возвращает (данные_монет, общая_капитализация, изменение_капитализации_24ч, сообщение_об_ошибке).
    """
    try:
        # 1. Глобальные данные
        global_url = f"{COINGECKO_API_BASE_URL}/global"
        r_global = requests.get(global_url, timeout=10, headers=COINGECKO_HEADERS)
        r_global.raise_for_status()
        global_data_cg_raw = r_global.json().get("data", {})
        total_market_cap_cg = global_data_cg_raw.get("total_market_cap", {}).get("usd") # Может быть 0
        market_cap_change_24h_cg = global_data_cg_raw.get("market_cap_change_percentage_24h_usd") # Может быть 0.0

        # 2. Топ N монет
        coins_url = (
            f"{COINGECKO_API_BASE_URL}/coins/markets"
            "?vs_currency=usd"
            "&order=market_cap_desc"
            f"&per_page={limit}"
            "&page=1"
            "&sparkline=false"
            "&price_change_percentage=24h"
        )
        r_coins = requests.get(coins_url, timeout=15, headers=COINGECKO_HEADERS)
        r_coins.raise_for_status()
        coins_data_cg = r_coins.json() 

        if not isinstance(coins_data_cg, list):
             return None, total_market_cap_cg, market_cap_change_24h_cg, "Некорректный формат ответа от CoinGecko (ожидался список)."
        
        # Поля уже соответствуют: symbol, name, current_price, price_change_percentage_24h, market_cap
        # В CoinGecko нет вложенности quote.USD, поля прямо в объекте монеты.

        return coins_data_cg, total_market_cap_cg, market_cap_change_24h_cg, None

    except requests.exceptions.HTTPError as http_err:
        return None, None, None, f"Ошибка HTTP CoinGecko: {http_err.response.status_code if http_err.response else 'Unknown'}"
    except requests.exceptions.Timeout:
        return None, None, None, "Таймаут CoinGecko."
    except requests.exceptions.RequestException as req_err:
        return None, None, None, f"Сетевая ошибка CoinGecko: {req_err}"
    except Exception as e: # Ловим более общие исключения
        print(f"CRITICAL: Unexpected error in _fetch_crypto_data_coingecko: {e}") # ЗАМЕНИТЬ НА log()
        # import traceback # Раскомментировать для детального трейсбека в логах
        # print(traceback.format_exc()) # ЗАМЕНИТЬ НА log()
        return None, None, None, f"Общая непредвиденная ошибка CoinGecko: {type(e).__name__}"


def get_global_crypto_market_data_text_formatted(total_market_cap, market_cap_change_24h, source_name=""):
    """
    Форматирует текст об общей капитализации крипторынка.
    """
    if total_market_cap is None or market_cap_change_24h is None:
        source_info_err = f" от {source_name}" if source_name else ""
        print(f"DEBUG: get_global_crypto_market_data_text_formatted - Incomplete data: total_market_cap={total_market_cap}, market_cap_change_24h={market_cap_change_24h}, source={source_name}") # ЗАМЕНИТЬ НА log()
        return f"🌍 Не удалось получить полные данные об общей капитализации крипторынка{source_info_err}."

    total_market_cap_formatted = format_large_number(total_market_cap)
    
    change_emoji = ""
    change_formatted_val = "N/A"
    try:
        change_val_float = float(market_cap_change_24h)
        if change_val_float > 0: change_emoji = "🟢 "
        elif change_val_float < 0: change_emoji = "🔴 "
        elif change_val_float == 0: change_emoji = "⚪ "
        change_formatted_val = f"{change_val_float:+.2f}%"
    except (ValueError, TypeError) as e:
        print(f"DEBUG: Error formatting market_cap_change_24h ('{market_cap_change_24h}'): {e}") # ЗАМЕНИТЬ НА log()
            
    source_info = f" (источник: {source_name})" if source_name else ""
    return (f"🌍 Общая капитализация крипторынка{source_info}: {total_market_cap_formatted}\n"
            f"   {change_emoji}Изменение за 24ч (глобально): {change_formatted_val}")

def get_crypto_data(extended=False):
    """
    Получает данные по топ-10 криптовалютам, сначала с CoinGecko, при неудаче с CoinMarketCap.
    """
    final_crypto_block_parts = []
    coins_data_list = None
    total_market_cap_val = None
    market_cap_change_24h_val = None
    source_name_used = ""

    print("INFO: Attempting to fetch crypto data from CoinGecko...") # ЗАМЕНИТЬ НА log()
    cg_coins, cg_total_cap, cg_cap_change, error_cg = _fetch_crypto_data_coingecko()
    
    if error_cg:
        print(f"WARNING: CoinGecko Error: {error_cg}") # ЗАМЕНИТЬ НА log()
        if COINMARKETCAP_API_KEY:
            print("INFO: CoinGecko failed. Attempting to fetch crypto data from CoinMarketCap...") # ЗАМЕНИТЬ НА log()
            cmc_coins, cmc_total_cap, cmc_cap_change, error_cmc = _fetch_crypto_data_cmc()
            if error_cmc:
                print(f"ERROR: CoinMarketCap Error: {error_cmc}") # ЗАМЕНИТЬ НА log()
                final_crypto_block_parts.append("❌ Не удалось получить данные по криптовалютам (оба источника недоступны). Подробности в логе.")
            else: # CMC успешен
                coins_data_list = cmc_coins
                total_market_cap_val = cmc_total_cap
                market_cap_change_24h_val = cmc_cap_change
                source_name_used = "CoinMarketCap"
                print("INFO: Successfully fetched crypto data from CoinMarketCap.") # ЗАМЕНИТЬ НА log()
        else: # CG не удался, CMC ключ не настроен
            print("WARNING: CoinGecko failed. CoinMarketCap API key not configured.") # ЗАМЕНИТЬ НА log()
            final_crypto_block_parts.append(f"❌ Ошибка CoinGecko. Резервный источник (CoinMarketCap) не настроен.")
    else: # CG успешен
        coins_data_list = cg_coins
        total_market_cap_val = cg_total_cap
        market_cap_change_24h_val = cg_cap_change
        source_name_used = "CoinGecko"
        print("INFO: Successfully fetched crypto data from CoinGecko.") # ЗАМЕНИТЬ НА log()

    if total_market_cap_val is not None and market_cap_change_24h_val is not None:
        global_market_text = get_global_crypto_market_data_text_formatted(total_market_cap_val, market_cap_change_24h_val, source_name_used)
        final_crypto_block_parts.append(global_market_text)
    elif not final_crypto_block_parts: # Если еще нет сообщений об ошибках (например, CG вернул None для глобальных, но не ошибку)
        err_src_name = source_name_used if source_name_used else "источников"
        final_crypto_block_parts.append(f"🌍 Данные об общей капитализации от {err_src_name} временно недоступны.")

    if coins_data_list is not None: # Если список есть (может быть пустым)
        today_date_str = date.today().strftime("%d.%m.%Y")
        source_info_coins = f" (источник: {source_name_used})" if source_name_used else ""
        top_coins_lines = [f"\n₿ Крипта на {today_date_str}{source_info_coins} (Топ-10 по капитализации)"]
        insights = []

        if not coins_data_list: # Если список пуст
             top_coins_lines.append(f"  ℹ️ Список топ-10 криптовалют пуст (или не получен) от {source_name_used}.")
        else:
            for coin_item in coins_data_list:
                symbol = coin_item.get("symbol", "N/A").upper()
                name = coin_item.get("name", "Unknown Coin")
                price_val = coin_item.get("current_price") # Для CG это прямое поле
                change_24h_coin = coin_item.get("price_change_percentage_24h") # Для CG это прямое поле
                market_cap_coin = coin_item.get("market_cap") # Для CG это прямое поле

                if price_val is None or change_24h_coin is None: # market_cap может быть None для некоторых монет
                    top_coins_lines.append(f"  {symbol}: ❌ неполные данные ({name}) от {source_name_used}")
                    continue
                
                price_formatted = "$0.0000"
                if price_val is not None:
                    try:
                        price_f = float(price_val)
                        if 0 < price_f < 1.0: price_formatted = f"${price_f:,.4f}"
                        elif price_f >= 1.0: price_formatted = f"${price_f:,.2f}"
                    except (ValueError, TypeError): pass 
                
                market_cap_formatted = f"(кап: {format_large_number(market_cap_coin)})" if market_cap_coin is not None else ""
                
                coin_change_emoji = ""
                change_24h_coin_float = 0.0 # Инициализируем для случая ошибки конвертации
                change_24h_coin_formatted = "N/A"
                try:
                    change_24h_coin_float = float(change_24h_coin)
                    if change_24h_coin_float > 0: coin_change_emoji = "🟢"
                    elif change_24h_coin_float < 0: coin_change_emoji = "🔴"
                    elif change_24h_coin_float == 0: coin_change_emoji = "⚪"
                    change_24h_coin_formatted = f"{change_24h_coin_float:+.2f}%"
                except (ValueError, TypeError): pass
                
                top_coins_lines.append(f"  {coin_change_emoji}<b>{symbol}</b>: {price_formatted} ({change_24h_coin_formatted}) {market_cap_formatted}")

                if extended and symbol not in STABLECOINS_TO_SKIP_ANALYSIS and isinstance(change_24h_coin_float, float):
                    if abs(change_24h_coin_float) >= 7:
                        direction = "растёт" if change_24h_coin_float > 0 else "падает"
                        insights.append(f"— {symbol} ({name}) {direction} более чем на {abs(change_24h_coin_float):.1f}%.")
                    elif 0 < abs(change_24h_coin_float) < 1 and change_24h_coin_float != 0: 
                        insights.append(f"— {symbol} ({name}) почти не изменился ({change_24h_coin_float:+.2f}%).")
            
        if extended:
            top_coins_lines.append("\n→ Краткий анализ по топ криптовалютам (исключая стейблкоины):")
            if insights:
                top_coins_lines.extend(insights)
            else: 
                top_coins_lines.append("— Среди отслеживаемых криптовалют (кроме стейблкоинов) значимых сигналов для анализа не выявлено.")

        try: # Блок для SMA BTC
            btc_ticker_yf = yf.Ticker("BTC-USD")
            btc_hist = btc_ticker_yf.history(period="8d")

            if not btc_hist.empty and len(btc_hist) >= 2:
                current_price_btc = btc_hist['Close'].iloc[-1]
                if len(btc_hist) >= 8:
                    sma7_btc = btc_hist['Close'].iloc[-8:-1].mean()
                    btc_price_fmt = format_large_number(current_price_btc).replace('$', '')
                    sma7_fmt = format_large_number(sma7_btc).replace('$', '')
                    btc_sma_info_line = f"\n💡 BTC ({btc_price_fmt}) "
                    if current_price_btc > sma7_btc: btc_sma_info_line += f"выше 7-дневной средней ({sma7_fmt})."
                    elif current_price_btc < sma7_btc: btc_sma_info_line += f"ниже 7-дневной средней ({sma7_fmt})."
                    else: btc_sma_info_line += f"на уровне 7-дневной средней ({sma7_fmt})."
                    top_coins_lines.append(btc_sma_info_line)
                else:
                    top_coins_lines.append(f"\n💡 Мало данных для SMA7 BTC (доступно {len(btc_hist)-1} пред. дн.).")
            else:
                top_coins_lines.append("\n💡 Нет исторических данных BTC (yfinance) для SMA.")
        except Exception as e_sma:
            print(f"WARNING: Ошибка при расчете SMA для BTC: {e_sma}") # ЗАМЕНИТЬ НА log()
            top_coins_lines.append("💡 Не удалось рассчитать 7-дневную среднюю для BTC.")
        
        final_crypto_block_parts.extend(top_coins_lines)

    elif not final_crypto_block_parts : # Если coins_data_list это None и ранее не было глобальных ошибок
         err_src_name = source_name_used if source_name_used else "источников"
         final_crypto_block_parts.append(f"ℹ️ Данные по топ криптовалютам от {err_src_name} не получены.")

    # Если после всех попыток final_crypto_block_parts все еще пуст
    if not final_crypto_block_parts:
        final_crypto_block_parts.append("❌ Данные по криптовалютам временно недоступны (общая ошибка).")

    return "\n".join(part for part in final_crypto_block_parts if part and part.strip())


def get_market_data_text():
    """
    Получает данные по фондовым индексам (ETF через Alpha Vantage, "чистые" индексы через yfinance).
    """
    result_parts = ["📊 Индексы и ETF"]
    etf_info_list = []

    if ALPHA_KEY:
        etf_tickers = {
            "S&P 500 ETF (SPY)": "SPY",
            "NASDAQ 100 ETF (QQQ)": "QQQ",
        }
        for name, symbol in etf_tickers.items():
            try:
                url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey={ALPHA_KEY}"
                r = requests.get(url, timeout=10)
                r.raise_for_status()
                data = r.json()
                quote = data.get("Global Quote")
                if not quote or not all(k in quote for k in ["05. price", "10. change percent"]) or not quote["05. price"]: # Добавил проверку на пустое значение цены
                    etf_info_list.append(f"  {name}: ❌ неполные/пустые данные (AlphaVantage)")
                    continue
                price = float(quote["05. price"])
                change_percent_str = quote["10. change percent"].rstrip('%')
                change_percent = float(change_percent_str)
                emoji = "🟢" if change_percent > 0 else "🔴" if change_percent < 0 else "⚪"
                etf_info_list.append(f"  {emoji}{name}: ${price:,.2f} ({change_percent:+.2f}%)")
            except requests.exceptions.RequestException as e: # Более специфичный обработчик для сетевых ошибок
                 etf_info_list.append(f"  {name}: ❌ ошибка сети ({type(e).__name__})")
            except ValueError as e: # Ошибка конвертации float/int
                 etf_info_list.append(f"  {name}: ❌ ошибка данных ({type(e).__name__})")
            except Exception as e: # Общий обработчик
                etf_info_list.append(f"  {name}: ❌ ошибка ({type(e).__name__})")
        
        if etf_info_list: result_parts.extend(etf_info_list)
        else: result_parts.append("  ⚠️ Не удалось загрузить данные по ETF (AlphaVantage). Проверьте ключ или доступность сервиса.") # Изменено сообщение
        result_parts.append("    └─ *ETF (Exchange Traded Fund) — это фонд, акции которого торгуются на бирже...")
    else:
        result_parts.append("  ℹ️ Alpha Vantage API ключ не настроен, данные по ETF не загружены.")

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
            # Для большей надежности используем ticker.info, если доступно, или history как fallback
            info = ticker.info
            current_price = info.get('regularMarketPrice', info.get('currentPrice'))
            prev_close = info.get('previousClose')

            if current_price is None or prev_close is None: # Если info не дало данных, пробуем history
                hist = ticker.history(period="5d")
                if not hist.empty and len(hist['Close'].dropna()) >= 2:
                    valid_closes = hist['Close'].dropna()
                    current_price = valid_closes.iloc[-1]
                    prev_close = valid_closes.iloc[-2]
                else:
                    index_info_list.append(f"  {name}: ❌ нет данных (yfinance)")
                    continue
            
            if current_price is None or prev_close is None or prev_close == 0: # Доп. проверка
                index_info_list.append(f"  {name}: ❌ некорректные данные (yfinance)")
                continue

            change = current_price - prev_close
            change_percent = (change / prev_close) * 100
            emoji = "🟢" if change_percent > 0 else "🔴" if change_percent < 0 else "⚪"
            index_info_list.append(f"  {emoji}{name}: {current_price:,.2f} pts ({change_percent:+.2f}%)")
        except Exception as e:
            index_info_list.append(f"  {name}: ❌ ошибка ({type(e).__name__})")

    if index_info_list:
        if etf_info_list or not ALPHA_KEY: result_parts.append("")
        result_parts.extend(index_info_list)
        result_parts.append("    └─ *Значения индексов выражаются в пунктах и являются «чистыми» статистическими величинами...")
    
    if len(result_parts) == 1:
         result_parts.append("  ⚠️ Не удалось загрузить данные по индексам и ETF.") # Изменено сообщение

    return "\n".join(result_parts)