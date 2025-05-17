import requests
import os
import datetime as dt

def get_crypto():
    try:
        ids = "bitcoin,ethereum"
        url = f"https://api.coingecko.com/api/v3/simple/price"
        params = {
            "ids": ids,
            "vs_currencies": "usd",
            "include_24hr_change": "true"
        }
        data = requests.get(url, params=params, timeout=10).json()
        btc = data["bitcoin"]["usd"]
        btc_chg = data["bitcoin"]["usd_24h_change"]
        eth = data["ethereum"]["usd"]
        eth_chg = data["ethereum"]["usd_24h_change"]
        return f"• BTC: ${btc:,.0f} ({btc_chg:+.1f}%)\n• ETH: ${eth:,.0f} ({eth_chg:+.1f}%)"
    except Exception as e:
        return f"Ошибка при получении курсов крипты: {e}"

def get_indices():
    try:
        alpha_key = os.getenv("ALPHA_KEY")
        symbols = {"S&P 500": "SPY", "DAX": "DAX"}
        result = []
        for name, sym in symbols.items():
            url = f"https://www.alphavantage.co/query"
            params = {
                "function": "GLOBAL_QUOTE",
                "symbol": sym,
                "apikey": alpha_key
            }
            r = requests.get(url, params=params, timeout=10).json()
            quote = r["Global Quote"]
            price = float(quote["05. price"])
            change = float(quote["10. change percent"].replace("%", ""))
            result.append(f"• {name}: ${price:,.2f} ({change:+.2f}%)")
        return "\n".join(result)
    except Exception as e:
        return f"Ошибка при получении индексов: {e}"

def get_market_data_text():
    today = dt.date.today().strftime("%d.%m.%Y")
    indices = get_indices()
    crypto = get_crypto()
    return f"""📈 Утренний обзор • {today}

Индексы 📊
{indices}

Крипта ₿
{crypto}
→ Что это значит для инвестора?
"""
