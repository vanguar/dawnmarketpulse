# whale_alert_reader.py

import requests
import os
from datetime import datetime

WHALE_KEY = os.getenv("WHALE_KEY")

def get_whale_activity_summary():
    if not WHALE_KEY:
        return "🐋 Whale Alert: API ключ не указан."

    url = "https://api.whale-alert.io/v1/transactions"
    params = {
        "api_key": WHALE_KEY,
        "min_value": 500000,
        "start": int(datetime.utcnow().timestamp()) - 86400,
        "limit": 20,
        "currency": "btc,usdt,usdc"
    }

    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        txs = data.get("transactions", [])
        result = []

        for tx in txs:
            amount = tx["amount"]
            currency = tx["symbol"].upper()

            from_data = tx.get("from", {}) or {}
            to_data = tx.get("to", {}) or {}

            from_owner_type = from_data.get("owner_type", "")
            from_owner_name = from_data.get("owner", "unknown")
            to_owner_type = to_data.get("owner_type", "")
            to_owner_name = to_data.get("owner", "unknown")

            # Форматирование имён
            from_display = (
                "неизвестной биржи" if from_owner_type == "exchange" and from_owner_name == "unknown"
                else f"кошелька ({from_owner_name[:8]}...)" if from_owner_type != "exchange"
                else from_owner_name
            )

            to_display = (
                "неизвестную биржу" if to_owner_type == "exchange" and to_owner_name == "unknown"
                else f"кошелька ({to_owner_name[:8]}...)" if to_owner_type != "exchange"
                else to_owner_name
            )

            # Определяем направление
            if from_owner_type == "exchange" and to_owner_type != "exchange":
                result.append(f"💸 Вывод {amount:,.0f} {currency} с {from_display}")
            elif to_owner_type == "exchange" and from_owner_type != "exchange":
                result.append(f"🐳 Ввод {amount:,.0f} {currency} на {to_display}")

        if not result:
            return "🐋 Нет крупных перемещений за сутки."

        return "\n".join(result[:5])

    except Exception as e:
        print(f"🐋 Ошибка Whale Alert: {e}")
        return f"🐋 Ошибка Whale Alert: {e}"
