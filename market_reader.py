import os
import requests

ALPHA_KEY = os.getenv("ALPHA_KEY")

def get_market_data_text():
    try:
        tickers = {
            "S&P 500": "SPY",
            "DAX": "DAX",
            "NASDAQ": "QQQ"
        }
        result = ["📊 Индексы"]
        for name, symbol in tickers.items():
            url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey={ALPHA_KEY}"
            r = requests.get(url, timeout=10)
            data = r.json()
            if "Global Quote" not in data or "05. price" not in data["Global Quote"]:
                result.append(f"{name}: ❌ ошибка")
                continue
            price = float(data["Global Quote"]["05. price"])
            change = float(data["Global Quote"]["10. change percent"].strip('%'))
            result.append(f"{name}: ${price:,.0f} ({change:+.1f}%)")
        return "\n".join(result)
    except Exception as e:
        return f"📊 Ошибка при получении индексов: {e}"

def get_crypto_data():
    try:
        symbols = {
            "BTC": "BTCUSDT",
            "ETH": "ETHUSDT"
        }
        result = ["₿ Крипта"]
        for name, pair in symbols.items():
            url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={pair}"
            r = requests.get(url, timeout=10)
            data = r.json()
            price = float(data["lastPrice"])
            change = float(data["priceChangePercent"])
            result.append(f"• {name}: ${price:,.0f} ({change:+.1f}%)")
        return "\n".join(result)
    except Exception as e:
        return f"₿ Ошибка при получении данных по крипте: {e}"
