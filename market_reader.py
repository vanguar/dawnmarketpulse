import os
import requests

ALPHA_KEY = os.getenv("ALPHA_KEY")

def get_market_data_text():
    try:
        tickers = {
            "S&P 500": "SPY",
            "DAX": "DAX",
            "NASDAQ": "IXIC"
        }

        result = ["📊 Индексы"]
        for name, symbol in tickers.items():
            url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey={ALPHA_KEY}"
            r = requests.get(url, timeout=10)
            data = r.json()

            if "Global Quote" not in data or "05. price" not in data["Global Quote"]:
                result.append(f"{name}: ❌ ошибка")
                continue

            price = data["Global Quote"]["05. price"]
            change = data["Global Quote"].get("10. change percent", "–")
            result.append(f"{name}: {price} ({change})")

        return "\n".join(result)

    except Exception as e:
        return f"📊 Индексы\nОшибка при получении данных: {e}"

