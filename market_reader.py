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

            price = float(data["Global Quote"]["05. price"])
            change = float(data["Global Quote"]["10. change percent"].replace("%", ""))
            emoji = "📈" if change > 0 else "📉"
            result.append(f"{emoji} {name}: ${price:.2f} ({change:+.2f}%)")

        return "\n".join(result)
    except Exception as e:
        return f"📊 Индексы\nОшибка при получении индексов: {e}"

def get_crypto_data():
    try:
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {
            "ids": "bitcoin,ethereum",
            "vs_currencies": "usd",
            "include_24hr_change": "true"
        }
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, params=params, headers=headers, timeout=10)
        data = r.json()

        btc = data["bitcoin"]
        eth = data["ethereum"]

        btc_price = btc["usd"]
        btc_change = btc["usd_24h_change"]
        eth_price = eth["usd"]
        eth_change = eth["usd_24h_change"]

        emoji_btc = "📈" if btc_change > 0 else "📉"
        emoji_eth = "📈" if eth_change > 0 else "📉"

        return (
            f"₿ Крипта\n"
            f"{emoji_btc} BTC: ${btc_price:,.0f} ({btc_change:+.1f}%)\n"
            f"{emoji_eth} ETH: ${eth_price:,.0f} ({eth_change:+.1f}%)"
        )
    except Exception as e:
        return f"₿ Крипта\nОшибка при получении данных: {e}"



