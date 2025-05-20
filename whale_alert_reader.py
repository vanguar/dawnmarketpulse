import os
import requests
from datetime import datetime, timedelta

BITQUERY_TOKEN = os.getenv("BITQUERY_TOKEN") # Убедитесь, что эта переменная установлена в вашей среде (например, в Railway)
BITQUERY_URL = "https://graphql.bitquery.io/"

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
      options: {{limit: 10, desc: "amountUsd"}} # Запрашиваем больше для большей вероятности найти валидные
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
      value: {{gt: 10}} # BTC value
      options: {{limit: 10, desc: "value"}} # Запрашиваем больше для большей вероятности найти валидные
    ) {{
      value
      address {{ address annotation owner }} # Получаем адрес выхода и его аннотации
      transaction {{
        hash
        blockTimestamp
        inputs(options: {{limit:50}}) {{ address {{address annotation owner}} }} # Получаем адреса входов
        outputs(options: {{limit:50}}) {{ address {{address annotation owner}} }} # И все выходы для анализа сдачи
      }}
    }}
  }}
}}"""}

def get_display_name(addr_obj): # Принимает объект адреса целиком
    if not addr_obj:
        return "???"
    
    addr = addr_obj.get("address")
    owner = addr_obj.get("owner")
    annotation = addr_obj.get("annotation")

    if owner:
        return str(owner)
    elif annotation:
        return str(annotation)
    elif addr:
        return f"{addr[:6]}...{addr[-4:]}"
    else:
        return "???"

def get_whale_activity_summary(debug=False):
    today = datetime.utcnow()
    yesterday = today - timedelta(days=1)
    date_from = yesterday.strftime("%Y-%m-%d")
    date_to = today.strftime("%Y-%m-%d")

    results = []
    
    if not BITQUERY_TOKEN:
        results.append("⚠️ BITQUERY_TOKEN не установлен. Данные по китам не могут быть загружены.")
        return "\n".join(results)

    processed_tx_hashes = set() # Для предотвращения дублирования транзакций, если они приходят из разных узлов запроса

    for net in NETWORKS:
        try:
            query = None
            if net["type"] == "transfers":
                query = build_transfer_query(net["slug"], date_from, date_to)
            elif net["type"] == "outputs": # Bitcoin
                query = build_btc_query(date_from, date_to)
            else:
                results.append(f"⚠️ [{net['name']}] Неподдерживаемый тип данных.")
                continue

            r = requests.post(BITQUERY_URL, headers=HEADERS, json=query, timeout=45)
            r.raise_for_status()
            data = r.json()

            if "errors" in data:
                error_details = str(data["errors"])
                results.append(f"❌ [{net['name']}] Ошибка API Bitquery: {error_details[:200]}") # Обрезаем длинные ошибки
                continue

            chain_data_key = net["slug"] if net["type"] != "outputs" else "bitcoin"
            chain_data = data.get("data", {}).get(chain_data_key)

            if chain_data is None: # Явная проверка на None
                results.append(f"ℹ️ [{net['name']}] Нет данных ('{chain_data_key}') в ответе Bitquery.")
                continue

            if net["type"] == "transfers":
                transfers = chain_data.get("transfers", [])
                
                if not transfers and "fallback_amount" in net: # Логика Fallback
                    query_fb = build_transfer_query(
                        net["slug"], date_from, date_to,
                        use_native=True,
                        native_limit=net["fallback_amount"]
                    )
                    r_fb = requests.post(BITQUERY_URL, headers=HEADERS, json=query_fb, timeout=45)
                    r_fb.raise_for_status() # Проверяем статус ответа
                    data_fb = r_fb.json()
                    if "errors" in data_fb:
                        error_details_fb = str(data_fb["errors"])
                        results.append(f"❌ [{net['name']}-Fallback] Ошибка API Bitquery: {error_details_fb[:200]}")
                        continue
                    
                    chain_data_fb = data_fb.get("data", {}).get(net["slug"])
                    if chain_data_fb is None: # Явная проверка на None
                        results.append(f"ℹ️ [{net['name']}] Fallback тоже не дал данных.")
                        continue
                    transfers = chain_data_fb.get("transfers", [])

                if not transfers:
                    results.append(f"ℹ️ [{net['name']}] Нет крупных транзакций после всех попыток.")
                    continue
                
                count = 0
                for tx in transfers:
                    if count >= 5: break

                    tx_hash = tx.get("transaction", {}).get("hash")
                    if tx_hash and tx_hash in processed_tx_hashes:
                        continue
                    
                    currency_obj = tx.get("currency")
                    if not currency_obj:
                        results.append(f"⚠️ [{net['name']}] Пропуск TX: нет данных о валюте. Хэш: {tx_hash or 'N/A'}")
                        continue
                    symbol = currency_obj.get("symbol", "???")

                    amount_val = tx.get("amount")
                    try:
                        amount_float = float(amount_val) if amount_val is not None else 0.0
                    except (ValueError, TypeError):
                        results.append(f"⚠️ [{net['name']}] Пропуск TX: неверный формат суммы '{amount_val}'. Хэш: {tx_hash or 'N/A'}")
                        continue
                    
                    if amount_float == 0.0 and not tx.get("amountUsd"): # Пропускаем нулевые суммы, если нет USD эквивалента
                        continue

                    sender_obj_raw = tx.get("sender") # tx.sender может быть объектом адреса
                    receiver_obj_raw = tx.get("receiver") # tx.receiver может быть объектом адреса

                    if not sender_obj_raw or not receiver_obj_raw:
                        results.append(f"⚠️ [{net['name']}] Пропуск TX: нет данных об отправителе/получателе. Хэш: {tx_hash or 'N/A'}")
                        continue
                    
                    sender_display = get_display_name(sender_obj_raw)
                    receiver_display = get_display_name(receiver_obj_raw)
                    
                    direction = "🔁" # По умолчанию
                    # Проверяем наличие owner или специфических аннотаций для определения ввода/вывода
                    if sender_obj_raw.get("owner") or ("exchange" in str(sender_obj_raw.get("annotation","")).lower()):
                        # Если отправитель - известный "owner" (биржа), это может быть вывод с биржи
                         if not (receiver_obj_raw.get("owner") or ("exchange" in str(receiver_obj_raw.get("annotation","")).lower())):
                            direction = "💸 Вывод" 
                    elif receiver_obj_raw.get("owner") or ("exchange" in str(receiver_obj_raw.get("annotation","")).lower()):
                        # Если получатель - известный "owner" (биржа), это может быть ввод на биржу
                        if not (sender_obj_raw.get("owner") or ("exchange" in str(sender_obj_raw.get("annotation","")).lower())):
                            direction = "🐳 Ввод"

                    results.append(f"{direction} [{net['name']}] {amount_float:,.0f} {symbol}: {sender_display} → {receiver_display}")
                    if tx_hash: processed_tx_hashes.add(tx_hash)
                    count += 1

            elif net["type"] == "outputs": # Bitcoin
                outputs_list = chain_data.get("outputs", [])
                if not outputs_list:
                    results.append(f"ℹ️ [Bitcoin] Нет крупных выводов (outputs).")
                    continue
                
                count = 0
                for btc_out in outputs_list:
                    if count >= 5: break
                    
                    tx_hash = btc_out.get("transaction", {}).get("hash")
                    if tx_hash and tx_hash in processed_tx_hashes:
                        continue

                    value_btc_str = btc_out.get("value")
                    try:
                        value_btc = float(value_btc_str) if value_btc_str is not None else 0.0
                    except (ValueError, TypeError):
                        results.append(f"⚠️ [Bitcoin] Пропуск Output: неверный формат value '{value_btc_str}'. Хэш: {tx_hash or 'N/A'}")
                        continue
                    if value_btc == 0.0: continue

                    # Для Bitcoin логика определения отправителя и получателя сложнее из-за UTXO
                    # Мы можем показать адрес выхода, который получил средства.
                    # Определение "реального" отправителя требует анализа всех входов.
                    
                    tx_detail_obj = btc_out.get("transaction")
                    output_address_obj = btc_out.get("address") # Адрес конкретного выхода

                    sender_display = "Несколько входов" # Упрощенное представление для Bitcoin
                    receiver_display = get_display_name(output_address_obj)

                    # Пытаемся найти "отправителя" по первому входу, если он не совпадает с одним из известных адресов получателя
                    # Это очень упрощенно!
                    if tx_detail_obj:
                        inputs = tx_detail_obj.get("inputs", [])
                        if inputs:
                            first_input_addr_obj = inputs[0].get("address")
                            # Проверяем, не является ли первый вход адресом сдачи для получателя (упрощенно)
                            if first_input_addr_obj and output_address_obj and first_input_addr_obj.get("address") != output_address_obj.get("address"):
                                sender_display_candidate = get_display_name(first_input_addr_obj)
                                # Избегаем ситуации, когда "отправитель" и "получатель" - это один и тот же отображаемый адрес, если не ???
                                if sender_display_candidate != receiver_display or receiver_display == "???":
                                     sender_display = sender_display_candidate


                    # Для Bitcoin часто используется "💸 Перевод" вместо "Вывод", так как это движение UTXO
                    results.append(f"💸 [Bitcoin] ~{value_btc:.2f} BTC: {sender_display} → {receiver_display} (Хэш: {tx_hash or 'N/A'})")
                    if tx_hash: processed_tx_hashes.add(tx_hash)
                    count +=1

        except requests.exceptions.HTTPError as http_err:
            results.append(f"⚠️ [{net['name']}] HTTP ошибка: {http_err.response.status_code} - {http_err.response.text[:100]}")
        except requests.exceptions.Timeout:
            results.append(f"⚠️ [{net['name']}] Таймаут запроса к Bitquery.")
        except requests.exceptions.RequestException as req_err:
            results.append(f"⚠️ [{net['name']}] Сетевая ошибка: {req_err}")
        except Exception as e:
            msg = f"⚠️ [{net['name']}] Общая ошибка: {str(e)}"
            if debug and 'r' in locals() and hasattr(r, 'text'): # Проверяем наличие 'r' и 'text'
                msg += f"\n   Ответ API: {r.text[:300]}" # Показываем часть ответа для дебага
            elif debug and 'r_fb' in locals() and hasattr(r_fb, 'text'):
                 msg += f"\n   Ответ API (fallback): {r_fb.text[:300]}"
            results.append(msg)

    if not results:
        return "🐋 Нет значимых транзакций китов за последние 24 часа."

    return "\n".join(results)