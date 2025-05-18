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
            change_percent_str = data["Global Quote"]["10. change percent"].rstrip('%')
            try:
                change_percent = float(change_percent_str)
                result.append(f"{name}: ${price:,.0f} ({change_percent:+.2f}%)")
            except ValueError:
                result.append(f"{name}: ${price:,.0f} ({data['Global Quote']['10. change percent']})")
    except Exception as e:
        result.append(f"Ошибка при получении индексов: {e}")

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
        r.raise_for_status()
        data = r.json()

        result = [f"₿ Крипта на {today}"]
        insights = []

        for name, cid in symbols.items():
            if cid not in data:
                result.append(f"{name}: ❌ нет данных от CoinGecko")
                continue

            price = data[cid].get("usd")
            change = data[cid].get("usd_24h_change")

            if price is None or change is None:
                result.append(f"{name}: ❌ неполные данные от CoinGecko")
                continue

            emoji = "📈" if change > 0 else "📉" if change < 0 else "📊"

            if 0 < price < 1.0:
                price_format = f"${price:,.4f}"
            elif price == 0 and name == "DOGE":
                price_format = "$0.0000"
            elif price == 0:
                price_format = "$0"
            else:
                price_format = f"${price:,.2f}"

            result.append(f"{emoji} {name}: {price_format} ({change:+.2f}%)")

            if extended:
                if abs(change) >= 5:
                    direction = "растёт" if change > 0 else "падает"
                    insights.append(f"— {name} {direction} более чем на 5%. Возможен разворот или пробой уровня.")
                elif 0 < abs(change) < 1:
                    insights.append(f"— {name} почти не меняется (изм. {change:+.2f}%). Возможна фаза накопления или флэта.")
                elif change == 0:
                    insights.append(f"— {name} без изменений за последние 24ч.")

        if extended and insights:
            result.append("\n→ Анализ:")
            result.extend(insights)

        return "\n".join(result)

    except requests.exceptions.HTTPError as http_err:
        return f"₿ Ошибка HTTP при получении криптовалют: {http_err}"
    except Exception as e:
        return f"₿ Ошибка при получении криптовалют: {e}"
