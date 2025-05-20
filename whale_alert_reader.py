import os
import requests
from datetime import datetime, timedelta

BITQUERY_TOKEN = os.getenv("BITQUERY_TOKEN")
BITQUERY_URL = "https://streaming.bitquery.io/graphql"

HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {BITQUERY_TOKEN}"
}

NETWORKS = [
    {"name": "Ethereum", "slug": "ethereum", "type": "transfers"},
    {"name": "BSC", "slug": "bsc", "type": "transfers"},
    {"name": "Polygon", "slug": "polygon", "type": "transfers"},
    {"name": "Tron", "slug": "tron", "type": "transfers"},
    {"name": "Solana", "slug": "solana", "type": "transfers", "fallback_amount": 25000},
    {"name": "XRP", "slug": "ripple", "type": "transfers", "fallback_amount": 1000000},
    {"name": "Bitcoin", "slug": "bitcoin", "type": "outputs"}
]

def build_transfer_query(network, date_from, date_to, use_native=False, native_limit=0):
    amount_filter = f"amount: {{gt: {native_limit}}}" if use_native else "amountUsd: {gt: 500000}"
    return {
        "query": f"""
{{
  {network} {{
    transfers(
      date: {{since: "{date_from}", till: "{date_to}"}}
      {amount_filter}
    ) {{
      amount
      amountUsd
      currency {{ symbol }}
      sender {{
        address
        annotation
        smartContract {{ contractType }}
        owner
      }}
      receiver {{
        address
        annotation
        smartContract {{ contractType }}
        owner
      }}
      transaction {{ hash blockTimestamp }}
    }}
  }}
}}"""}

def build_btc_query(date_from, date_to):
    return {
        "query": f"""
{{
  bitcoin {{
    outputs(
      date: {{since: "{date_from}", till: "{date_to}"}}
      value: {{gt: 10}}
    ) {{
      value
      transaction {{
        hash
        blockTimestamp
        inputs {{ address }}
        outputs {{ address }}
      }}
    }}
  }}
}}"""}

def get_display_name(addr, owner, annotation):
    if owner:
        return f"{owner}"
    elif annotation:
        return f"{annotation}"
    else:
        return f"{addr[:6]}...{addr[-4:]}" if addr else "???"

def get_whale_activity_summary():
    today = datetime.utcnow()
    yesterday = today - timedelta(days=1)
    date_from = yesterday.strftime("%Y-%m-%d")
    date_to = today.strftime("%Y-%m-%d")

    results = []

    for net in NETWORKS:
        try:
            if net["type"] == "transfers":
                query = build_transfer_query(net["slug"], date_from, date_to)
            elif net["type"] == "outputs":
                query = build_btc_query(date_from, date_to)

            r = requests.post(BITQUERY_URL, headers=HEADERS, json=query, timeout=30)
            r.raise_for_status()
            data = r.json()

            if net["type"] == "transfers":
                transfers = data.get("data", {}).get(net["slug"], {}).get("transfers", [])
                # fallback если пусто и нужна вторая попытка
                if not transfers and "fallback_amount" in net:
                    query = build_transfer_query(
                        net["slug"], date_from, date_to,
                        use_native=True,
                        native_limit=net["fallback_amount"]
                    )
                    r = requests.post(BITQUERY_URL, headers=HEADERS, json=query, timeout=30)
                    r.raise_for_status()
                    data = r.json()
                    transfers = data.get("data", {}).get(net["slug"], {}).get("transfers", [])

                for tx in transfers[:5]:
                    symbol = tx["currency"]["symbol"]
                    amount = float(tx["amount"])
                    sender_addr = tx["sender"]["address"]
                    receiver_addr = tx["receiver"]["address"]
                    sender = get_display_name(sender_addr, tx["sender"].get("owner"), tx["sender"].get("annotation"))
                    receiver = get_display_name(receiver_addr, tx["receiver"].get("owner"), tx["receiver"].get("annotation"))
                    direction = "🔁"

                    if tx["receiver"].get("owner"):
                        direction = "🐳 Ввод"
                    elif tx["sender"].get("owner"):
                        direction = "💸 Вывод"

                    results.append(f"{direction} [{net['name']}] {amount:,.0f} {symbol}: {sender} → {receiver}")

            elif net["type"] == "outputs":
                transfers = data.get("data", {}).get("bitcoin", {}).get("outputs", [])
                for tx in transfers[:5]:
                    txdata = tx["transaction"]
                    value_btc = float(tx["value"])
                    inputs = txdata.get("inputs", [])
                    outputs = txdata.get("outputs", [])
                    input_addrs = {i["address"] for i in inputs}
                    output_addrs = {o["address"] for o in outputs}

                    # исключаем change: если адрес есть и там, и там — это сдача
                    true_outputs = output_addrs - input_addrs

                    sender = next(iter(input_addrs)) if input_addrs else "unknown"
                    receiver = next(iter(true_outputs)) if true_outputs else "unknown"

                    results.append(f"💸 [Bitcoin] ~{value_btc:.2f} BTC: {sender[:6]}... → {receiver[:6]}...")

        except Exception as e:
            results.append(f"⚠️ [{net['name']}] Ошибка: {e}")

    if not results:
        return "🐋 Нет крупных транзакций за последние 24 часа."

    return "\n".join(results)
