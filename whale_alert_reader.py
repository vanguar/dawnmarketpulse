import os
import requests
from datetime import datetime, timedelta

BITQUERY_TOKEN = os.getenv("BITQUERY_TOKEN")
BITQUERY_URL = "https://graphql.bitquery.io/"

HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {BITQUERY_TOKEN}"
}

NETWORKS = [
    {"name": "Ethereum", "type": "transfers", "query_root_field": "ethereum", "network_arg": "eth"},
    {"name": "BSC", "type": "transfers", "query_root_field": "ethereum", "network_arg": "bsc"},
    {"name": "Polygon", "type": "transfers", "query_root_field": "ethereum", "network_arg": "matic"},
    {"name": "Tron", "type": "transfers", "query_root_field": "tron"},
    {"name": "Solana", "type": "transfers", "query_root_field": "solana"},
    {"name": "XRP", "type": "transfers", "query_root_field": "ripple"},
    {"name": "Bitcoin", "type": "outputs", "query_root_field": "bitcoin"}
]

def build_query_for_network(net_config, date_from, date_to):
    root_field = net_config["query_root_field"]
    network_arg_value = net_config.get("network_arg")

    fields_common_transfers = """
        amount
        amountUsd
        currency { symbol }
        sender { address annotation smartContract { contractType } owner }
        receiver { address annotation smartContract { contractType } owner }
        transaction { hash blockTimestamp }
    """

    fields_bitcoin_outputs = """
        value
        address { address annotation owner }
        transaction {
          hash
          blockTimestamp
          inputs(options: {limit:50}) { address {address annotation owner} }
          outputs(options: {limit:50}) { address {address annotation owner} }
        }
    """

    if net_config["type"] == "transfers":
        field_to_query_in_root = "transfers"
        fields_to_select = fields_common_transfers
    elif net_config["type"] == "outputs":
        field_to_query_in_root = "outputs"
        fields_to_select = fields_bitcoin_outputs
    else:
        raise ValueError(f"Неизвестный тип данных: {net_config['type']}")

    # В API запросе остается только аргумент date для transfers/outputs
    query_arguments_for_field = f'date: {{since: "{date_from}", till: "{date_to}"}}'

    if root_field == "ethereum" and network_arg_value:
        # Используем кавычки для network_arg_value, т.к. это строковый аргумент в GraphQL
        query_body = f"""
        {root_field}(network: \"{network_arg_value}\") {{
          {field_to_query_in_root}({query_arguments_for_field}) {{
            {fields_to_select}
          }}
        }}
        """
    else:
        query_body = f"""
        {root_field} {{
          {field_to_query_in_root}({query_arguments_for_field}) {{
            {fields_to_select}
          }}
        }}
        """
    return {"query": f"{{ {query_body} }}"}

def get_display_name(addr_obj):
    if not addr_obj: return "???"
    addr = addr_obj.get("address")
    owner = addr_obj.get("owner")
    annotation = addr_obj.get("annotation")
    if owner: return str(owner)
    if annotation: return str(annotation)
    if addr: return f"{addr[:6]}...{addr[-4:]}"
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

    processed_tx_hashes = set()

    for net_config in NETWORKS:
        net_name = net_config["name"]
        try:
            query = build_query_for_network(net_config, date_from, date_to)
            
            r = requests.post(BITQUERY_URL, headers=HEADERS, json=query, timeout=60)
            r.raise_for_status()
            data = r.json()

            if "errors" in data:
                error_details = str(data["errors"])
                results.append(f"❌ [{net_name}] Ошибка API Bitquery: {error_details[:200]}")
                continue

            data_level1 = data.get("data", {})
            chain_data_container = data_level1.get(net_config["query_root_field"])

            if chain_data_container is None:
                results.append(f"ℹ️ [{net_name}] Нет данных для корневого поля ('{net_config['query_root_field']}') в ответе Bitquery.")
                continue

            raw_list_from_api = []
            if net_config["type"] == "transfers":
                raw_list_from_api = chain_data_container.get("transfers", [])
            elif net_config["type"] == "outputs":
                raw_list_from_api = chain_data_container.get("outputs", [])

            if not raw_list_from_api:
                results.append(f"ℹ️ [{net_name}] API вернул пустой список транзакций/выходов.")
                continue

            # --- Локальная фильтрация ---
            locally_filtered_list = []
            if net_config["type"] == "transfers":
                USD_FILTER_THRESHOLD = 500000.0
                for tx_item in raw_list_from_api:
                    amount_usd_str = tx_item.get("amountUsd")
                    if amount_usd_str is not None:
                        try:
                            if float(amount_usd_str) >= USD_FILTER_THRESHOLD:
                                locally_filtered_list.append(tx_item)
                        except (ValueError, TypeError):
                            pass # Игнорируем ошибки конвертации
                
                # Локальная сортировка
                locally_filtered_list.sort(key=lambda x: float(x.get("amountUsd", 0) or 0), reverse=True)

            elif net_config["type"] == "outputs": # Bitcoin
                BTC_FILTER_THRESHOLD = 10.0
                for tx_item in raw_list_from_api:
                    value_btc_str = tx_item.get("value")
                    if value_btc_str is not None:
                        try:
                            if float(value_btc_str) >= BTC_FILTER_THRESHOLD:
                                locally_filtered_list.append(tx_item)
                        except (ValueError, TypeError):
                            pass # Игнорируем ошибки конвертации
                locally_filtered_list.sort(key=lambda x: float(x.get("value", 0) or 0), reverse=True)
            
            if not locally_filtered_list:
                results.append(f"ℹ️ [{net_name}] Нет крупных транзакций (после локальной фильтрации и сортировки).")
                continue
            
            # --- Обработка и вывод топ-5 ---
            count = 0
            for tx_item in locally_filtered_list:
                if count >= 5: break
                tx_hash = tx_item.get("transaction", {}).get("hash")
                if tx_hash and tx_hash in processed_tx_hashes: # Проверяем tx_hash на None перед добавлением
                    continue
                if tx_hash: # Добавляем только если хэш есть
                    processed_tx_hashes.add(tx_hash)
                
                if net_config["type"] == "transfers":
                    currency_obj = tx_item.get("currency")
                    symbol = currency_obj.get("symbol", "???") if currency_obj else "???"
                    
                    # Отображаем amountUsd, если он есть и прошел фильтр, иначе просто amount (если есть)
                    amount_usd_val = tx_item.get("amountUsd")
                    amount_val = tx_item.get("amount")
                    amount_to_display = 0.0
                    display_currency_symbol = symbol

                    if amount_usd_val is not None:
                        try:
                            amount_to_display = float(amount_usd_val)
                            if symbol != "???":
                                display_currency_symbol = f"USD ({symbol})"
                            else:
                                display_currency_symbol = "USD"
                        except (ValueError, TypeError): # Если amountUsd не число, пробуем amount
                            if amount_val is not None:
                                try:
                                    amount_to_display = float(amount_val)
                                except (ValueError, TypeError): pass # amount тоже не число
                            
                    elif amount_val is not None: # amountUsd отсутствует, используем amount
                         try:
                            amount_to_display = float(amount_val)
                         except (ValueError, TypeError): pass

                    sender_obj_raw = tx_item.get("sender")
                    receiver_obj_raw = tx_item.get("receiver")
                    if not sender_obj_raw or not receiver_obj_raw: continue # Маловероятно после фильтрации, но для безопасности
                    
                    sender_display = get_display_name(sender_obj_raw)
                    receiver_display = get_display_name(receiver_obj_raw)
                    
                    direction = "🔁" # Упрощенная логика ChatGPT
                    if "exchange" in str(sender_obj_raw.get("annotation", "")).lower():
                        direction = "💸 Вывод"
                    elif "exchange" in str(receiver_obj_raw.get("annotation", "")).lower():
                        direction = "🐳 Ввод"
                    results.append(f"{direction} [{net_name}] {amount_to_display:,.0f} {display_currency_symbol}: {sender_display} → {receiver_display}")

                elif net_config["type"] == "outputs": # Bitcoin
                    value_btc = 0.0
                    value_btc_str = tx_item.get("value")
                    if value_btc_str is not None:
                        try: value_btc = float(value_btc_str)
                        except (ValueError, TypeError): pass

                    tx_detail_obj = tx_item.get("transaction")
                    output_address_obj = tx_item.get("address")
                    sender_display = "Несколько входов" # Упрощенно
                    receiver_display = get_display_name(output_address_obj)

                    if tx_detail_obj: # Безопасный доступ к inputs
                        inputs = tx_detail_obj.get("inputs", [])
                        if inputs and inputs[0]: # Проверяем, что список не пуст и первый элемент существует
                            first_input_addr_obj = inputs[0].get("address")
                            # Дальнейшая логика для sender_display как в моей предыдущей версии, если нужна
                            if first_input_addr_obj and output_address_obj and first_input_addr_obj.get("address") != output_address_obj.get("address"):
                                sender_display_candidate = get_display_name(first_input_addr_obj)
                                if sender_display_candidate != receiver_display or receiver_display == "???":
                                     sender_display = sender_display_candidate

                    results.append(f"💸 [{net_name}] ~{value_btc:.2f} BTC: {sender_display} → {receiver_display} (Хэш: {tx_hash or 'N/A'})")

                count += 1
        
        except requests.exceptions.HTTPError as http_err:
            results.append(f"⚠️ [{net_name}] HTTP ошибка: {http_err.response.status_code} - {http_err.response.text[:100]}")
        except requests.exceptions.Timeout:
            results.append(f"⚠️ [{net_name}] Таймаут запроса к Bitquery.")
        except requests.exceptions.RequestException as req_err:
            results.append(f"⚠️ [{net_name}] Сетевая ошибка: {req_err}")
        except Exception as e:
            msg = f"⚠️ [{net_name}] Общая ошибка: {str(e)}"
            if debug:
                response_text = None
                # r_fb убран, т.к. fallback упрощен/удален из этого потока
                if 'r' in locals() and hasattr(r, 'text'): response_text = r.text
                if response_text: msg += f"\n   Ответ API: {response_text[:300]}"
            results.append(msg)

    if not results:
        return "🐋 Нет данных по крупным транзакциям после всех попыток и фильтрации."
    return "\n".join(results)