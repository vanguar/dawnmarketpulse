# metrics_reader.py

import requests

def get_long_short_ratio(symbol="BTCUSDT"):
    try:
        url = "https://fapi.binance.com/futures/data/globalLongShortAccountRatio"
        params = {"symbol": symbol, "period": "1h", "limit": 1}
        r = requests.get(url, params=params, timeout=10)
        data = r.json()[0]
        long_pct = float(data["longAccount"]) * 100
        short_pct = float(data["shortAccount"]) * 100
        return f"⚖️ {symbol}: Лонги {long_pct:.1f}% / Шорты {short_pct:.1f}%"
    except Exception as e:
        return f"⚖️ Ошибка {symbol}: {e}"

def get_derivatives_block():
    return "\n".join([
        get_long_short_ratio("BTCUSDT"),
        get_long_short_ratio("ETHUSDT")
    ])
