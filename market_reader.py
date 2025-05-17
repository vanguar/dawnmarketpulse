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

def get_crypto_data(extended=False):
    try:
        symbols = {
            "BTC": "BTCUSDT",
            "ETH": "ETHUSDT"
        }
        result = ["₿ Крипта"]
        insights = []

        for name, pair in symbols.items():
            url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={pair}"
            r = requests.get(url, timeout=10)
            data = r.json()
            price = float(data["lastPrice"])
            change = float(data["priceChangePercent"])
            emoji = "📈" if change > 0 else "📉"
            result.append(f"{emoji} {name}: ${price:,.0f} ({change:+.1f}%)")

            if extended:
                if abs(change) > 3:
                    direction = "рост" if change > 0 else "снижение"
                    insights.append(f"— {name} показывает {direction} более чем на 3%. Это может быть сигналом краткосрочного импульса.")
                elif abs(change) < 0.5:
                    insights.append(f"— {name} почти без изменений. Возможно, формируется консолидация.")

        if extended and insights:
            result.append("\n→ Анализ:")
            result.extend(insights)

        return "\n".join(result)
    except Exception as e:
        return f"₿ Ошибка при получении данных по крипте: {e}"
