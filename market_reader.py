
import os
import requests
from datetime import date

ALPHA_KEY = os.getenv("ALPHA_KEY")

def get_market_data_text():
    result = ["📊 Индексы"]
    try:
        tickers = {
            "S&P 500": "SPY",
            "DAX": "DAX",
            "NASDAQ": "QQQ"
        }

        for name, symbol in tickers.items():
            url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey={ALPHA_KEY}"
            r = requests.get(url, timeout=10)
            data = r.json()
            if "Global Quote" not in data or "05. price" not in data["Global Quote"]:
                result.append(f"{name}: ❌ ошибка")
                continue
            price = float(data["Global Quote"]["05. price"])
            change_percent = data["Global Quote"]["10. change percent"]
            result.append(f"{name}: ${price:.0f} ({change_percent})")
    except Exception:
        result.append("Ошибка при получении индексов.")

    return "\n".join(result)

def get_crypto_data(extended=False):
    try:
        today = date.today().strftime("%d.%m.%Y")
        symbols = {
            "BTC": "bitcoin",
            "ETH": "ethereum",
            "SOL": "solana",
            "DOGE": "dogecoin"
        }

        url = (
            "https://api.coingecko.com/api/v3/simple/price"
            "?ids=bitcoin,ethereum,solana,dogecoin"
            "&vs_currencies=usd"
            "&include_24hr_change=true"
        )
        r = requests.get(url, timeout=10)
        data = r.json()

        result = [f"₿ Крипта на {today}"]
        insights = []

        for name, cid in symbols.items():
            price = data[cid]["usd"]
            change = data[cid]["usd_24h_change"]
            emoji = "📈" if change > 0 else "📉"
            result.append(f"{emoji} {name}: ${price:,.0f} ({change:+.2f}%)")

            if extended:
                if abs(change) >= 5:
                    direction = "растёт" if change > 0 else "падает"
                    insights.append(
                        f"— {name} {direction} более чем на 5%. Возможен разворот или пробой уровня.")
                elif abs(change) < 1:
                    insights.append(f"— {name} почти не меняется. Возможна фаза накопления или флэта.")

        if extended and insights:
            result.append("\n→ Анализ:")
            result.extend(insights)

        return "\n".join(result)

    except Exception as e:
        return f"₿ Ошибка при получении криптовалют: {e}"
