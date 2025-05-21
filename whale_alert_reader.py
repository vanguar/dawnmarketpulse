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
    {"name": "Ethereum", "type": "transfers", "query_root_field": "ethereum", "network_arg": "ethereum"}, # Изменено с "eth"
    {"name": "BSC", "type": "transfers", "query_root_field": "ethereum", "network_arg": "bsc"},
    {"name": "Polygon", "type": "transfers", "query_root_field": "ethereum", "network_arg": "matic"},
    {"name": "Tron", "type": "transfers", "query_root_field": "tron"},
    {"name": "Solana", "type": "transfers", "query_root_field": "solana"},
    {"name": "XRP", "type": "transfers", "query_root_field": "ripple"}, # Используем 'ripple' как query_root_field для XRP
    {"name": "Bitcoin", "type": "outputs", "query_root_field": "bitcoin"}
]

def build_query_for_network(net_config, date_from, date_to):
    root_field = net_config["query_root_field"]
    network_arg_value = net_config.get("network_arg")

    # Основные поля, общие для большинства запросов transfers (кроме суммы и специфичных для сети полей валюты)
    base_fields_transfers_core = """
        block { timestamp { iso8601 } }
        receiver { address annotation smartContract { contractType } owner }
        sender { address annotation smartContract { contractType } owner }
        transaction { hash blockTimestamp }
    """

    # Поля суммы и валюты, специфичные для сети
    amount_field_query_part = ""
    currency_fields_query_part = ""

    if net_config["name"] == "Tron" or net_config["name"] == "Solana":
        amount_field_query_part = "amount"
        currency_fields_query_part = "currency { address name symbol }"
    elif net_config["name"] == "XRP":
        amount_field_query_part = "amountUsd: amountFrom(in: USD)" # Псевдоним для удобства обработки
        currency_fields_query_part = "currencyFrom { address name symbol }" # Используем currencyFrom для XRP
    else: # Для Ethereum, BSC, Polygon и других (если будут)
        amount_field_query_part = "amountUsd" # По умолчанию пробуем amountUsd
        currency_fields_query_part = "currency { address name symbol }"


    fields_to_select_transfers = f"""
        {amount_field_query_part}
        {currency_fields_query_part}
        {base_fields_transfers_core}
    """

    # Поля для Bitcoin outputs
    fields_bitcoin_outputs = """
        value
        outputAddress { # Изменено с 'address' на 'outputAddress'
            address
            annotation
        }
        block { # Добавлено для получения времени блока, как в примере API
            timestamp {
                iso8601
            }
        }
        transaction { # Содержит хеш транзакции и опционально входы для определения отправителя
          hash
          # blockTimestamp # Можно удалить, если используется block.timestamp.iso8601 выше
          inputs(options: {limit:1}) { # Запрашиваем только 1 вход для эвристики отправителя
            inputAddress { # Изменено с 'address' на 'inputAddress'
                address
                annotation
            }
            value # Сумма этого входа
          }
        }
    """

    if net_config["type"] == "transfers":
        field_to_query_in_root = "transfers"
        fields_to_select = fields_to_select_transfers
    elif net_config["type"] == "outputs":
        field_to_query_in_root = "outputs"
        fields_to_select = fields_bitcoin_outputs
    else:
        raise ValueError(f"Неизвестный тип данных: {net_config['type']}")

    query_arguments_for_field = f'date: {{since: "{date_from}", till: "{date_to}"}}'

    if root_field == "ethereum" and network_arg_value:
        # Для Enum типов кавычки не нужны, значение передается как литерал
        query_body = f"""
        {root_field}(network: {network_arg_value}) {{
          {field_to_query_in_root}({query_arguments_for_field}, options: {{limit: 100, desc: "{amount_field_query_part}"}}) {{ # Добавил options для сортировки и лимита
            {fields_to_select}
          }}
        }}
        """
    elif root_field == "ripple" and net_config["type"] == "transfers": # XRP
        # Для XRP аргумент network также может быть нужен для корневого поля ripple
        # и options могут отличаться
        query_body = f"""
        {root_field}(network: {network_arg_value or "ripple"}) {{
          {field_to_query_in_root}({query_arguments_for_field}, options: {{limit: 100, desc: "block"}}) {{ # Пример desc по block
            {fields_to_select}
          }}
        }}
        """
    elif root_field == "bitcoin" and net_config["type"] == "outputs": # Bitcoin
         query_body = f"""
        {root_field} {{
          {field_to_query_in_root}({query_arguments_for_field}, options: {{limit: 100, desc: "value"}}) {{ # Сортировка по value
            {fields_to_select}
          }}
        }}
        """
    else: # Tron, Solana и другие, не требующие network в корневом поле (или если network_arg не задан)
        # Добавляем options для сортировки и лимита, если применимо
        # Для Tron/Solana amount_field_query_part будет 'amount'
        sort_field = amount_field_query_part if amount_field_query_part == "amount" else "block" # Примерная логика сортировки
        query_body = f"""
        {root_field} {{
          {field_to_query_in_root}({query_arguments_for_field}, options: {{limit: 100, desc: "{sort_field}"}}) {{
            {fields_to_select}
          }}
        }}
        """
    return {"query": f"{{ {query_body} }}"}


def get_display_name(addr_obj):
    if not addr_obj: return "???"
    addr = addr_obj.get("address")
    owner = addr_obj.get("owner") # 'owner' может отсутствовать для outputAddress/inputAddress
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
                # Это сообщение может быть слишком частым, если нет транзакций, можно сделать менее подробным или убрать
                # results.append(f"ℹ️ [{net_name}] API вернул пустой список транзакций/выходов.")
                continue

            locally_filtered_list = []
            if net_config["type"] == "transfers":
                USD_FILTER_THRESHOLD = 500000.0 # Этот фильтр будет работать только для сетей, где мы получаем amountUsd
                for tx_item in raw_list_from_api:
                    # Для Tron/Solana amountUsd будет None, так как мы запрашиваем 'amount'
                    # Для XRP amountUsd - это псевдоним для amountFrom(in: USD)
                    amount_usd_val = tx_item.get("amountUsd")
                    
                    if amount_usd_val is not None: # Фильтруем по USD, если есть
                        try:
                            if float(amount_usd_val) >= USD_FILTER_THRESHOLD:
                                locally_filtered_list.append(tx_item)
                        except (ValueError, TypeError):
                            pass
                    elif net_config["name"] in ["Tron", "Solana"]:
                        # Для Tron и Solana amountUsd не запрашивается, поэтому локальный USD-фильтр не применяется.
                        # Если нужна фильтрация для них, ее нужно делать на основе 'amount' и текущего курса токена.
                        # Пока просто добавляем все, если нет USD-фильтра. Можно добавить другой тип фильтра, если нужно.
                        locally_filtered_list.append(tx_item) # Временно добавляем все, если нет amountUsd
                
                # Локальная сортировка (если нужна после API сортировки)
                # Для Tron/Solana amountUsd будет None. Сортировка по amountUsd не будет для них работать.
                locally_filtered_list.sort(key=lambda x: float(x.get("amountUsd", 0) or 0), reverse=True)


            elif net_config["type"] == "outputs": # Bitcoin
                BTC_FILTER_THRESHOLD = 10.0 # 10 BTC
                for tx_item in raw_list_from_api:
                    value_btc_str = tx_item.get("value")
                    if value_btc_str is not None:
                        try:
                            if float(value_btc_str) >= BTC_FILTER_THRESHOLD:
                                locally_filtered_list.append(tx_item)
                        except (ValueError, TypeError):
                            pass
                locally_filtered_list.sort(key=lambda x: float(x.get("value", 0) or 0), reverse=True)
            
            if not locally_filtered_list:
                # results.append(f"ℹ️ [{net_name}] Нет крупных транзакций (после локальной фильтрации и сортировки).")
                continue
            
            count = 0
            for tx_item in locally_filtered_list:
                if count >= 5: break # Выводим топ-5 после фильтрации и сортировки
                
                tx_hash_obj = tx_item.get("transaction", {})
                tx_hash = tx_hash_obj.get("hash") if tx_hash_obj else None # Для Bitcoin outputs transaction может быть None

                if tx_hash and tx_hash in processed_tx_hashes:
                    continue
                if tx_hash:
                    processed_tx_hashes.add(tx_hash)
                
                if net_config["type"] == "transfers":
                    amount_val = tx_item.get("amount")
                    amount_usd_val = tx_item.get("amountUsd")

                    amount_to_display = 0.0
                    
                    currency_obj_retrieved = None
                    if net_config["name"] == "XRP":
                        currency_obj_retrieved = tx_item.get("currencyFrom")
                    else:
                        currency_obj_retrieved = tx_item.get("currency")
                    
                    display_currency_symbol = currency_obj_retrieved.get("symbol", "???") if currency_obj_retrieved else "???"

                    if net_config["name"] == "XRP":
                        if amount_usd_val is not None:
                            try:
                                amount_to_display = float(amount_usd_val)
                                original_symbol = currency_obj_retrieved.get("symbol", "???") if currency_obj_retrieved else "???"
                                if original_symbol and original_symbol.upper() != "USD":
                                     display_currency_symbol = f"USD (эквив. {original_symbol})"
                                else:
                                     display_currency_symbol = "USD"
                            except (ValueError, TypeError): pass
                    elif net_config["name"] == "Tron" or net_config["name"] == "Solana":
                        if amount_val is not None:
                            try: amount_to_display = float(amount_val)
                            except (ValueError, TypeError): pass
                        # display_currency_symbol уже установлен из currency.symbol
                    else: # ETH, BSC, Polygon
                        if amount_usd_val is not None:
                            try:
                                amount_to_display = float(amount_usd_val)
                                original_symbol = currency_obj_retrieved.get("symbol", "???") if currency_obj_retrieved else "???"
                                if original_symbol and original_symbol.upper() != "USD":
                                    display_currency_symbol = f"USD ({original_symbol})"
                                else:
                                    display_currency_symbol = "USD"
                            except (ValueError, TypeError):
                                if amount_val is not None: # Фоллбэк на amount
                                    try: amount_to_display = float(amount_val)
                                    except (ValueError, TypeError): pass
                        elif amount_val is not None:
                             try: amount_to_display = float(amount_val)
                             except (ValueError, TypeError): pass
                    
                    sender_obj_raw = tx_item.get("sender")
                    receiver_obj_raw = tx_item.get("receiver")
                    if not sender_obj_raw or not receiver_obj_raw: continue
                    
                    sender_display = get_display_name(sender_obj_raw)
                    receiver_display = get_display_name(receiver_obj_raw)
                    
                    direction_emoji = "🔁"
                    if "exchange" in str(sender_obj_raw.get("annotation", "")).lower() or \
                       "exchange" in str(sender_obj_raw.get("owner", "")).lower(): # Проверяем и annotation, и owner
                        direction_emoji = "💸 Вывод"
                    elif "exchange" in str(receiver_obj_raw.get("annotation", "")).lower() or \
                         "exchange" in str(receiver_obj_raw.get("owner", "")).lower():
                        direction_emoji = "🐳 Ввод"
                    
                    # Пропускаем транзакции с нулевой суммой после всех преобразований
                    if amount_to_display == 0:
                        continue

                    results.append(f"{direction_emoji} [{net_name}] {amount_to_display:,.0f} {display_currency_symbol}: {sender_display} → {receiver_display}")

                elif net_config["type"] == "outputs": # Bitcoin
                    value_btc = 0.0
                    value_btc_str = tx_item.get("value")
                    if value_btc_str is not None:
                        try: value_btc = float(value_btc_str)
                        except (ValueError, TypeError): pass

                    if value_btc == 0: # Пропускаем нулевые выходы
                        continue

                    tx_detail_obj = tx_item.get("transaction")
                    output_address_obj_from_item = tx_item.get("outputAddress")
                    receiver_display = get_display_name(output_address_obj_from_item)

                    sender_display = "Новые BTC" # Bitcoin outputs often from multiple inputs or coinbase
                    if tx_detail_obj:
                        inputs = tx_detail_obj.get("inputs", [])
                        if inputs and inputs[0]:
                            first_input_addr_obj = inputs[0].get("inputAddress")
                            if first_input_addr_obj: # Если есть информация о первом входе
                                sender_display_candidate = get_display_name(first_input_addr_obj)
                                if sender_display_candidate != "???" and (sender_display_candidate != receiver_display or receiver_display == "???"):
                                    sender_display = sender_display_candidate
                                elif sender_display_candidate == "???": # Если первый вход неизвестен
                                     sender_display = "Неизв. источник"
                    
                    current_tx_hash = tx_detail_obj.get("hash") if tx_detail_obj else None

                    results.append(f"💰 [{net_name}] ~{value_btc:.2f} BTC: {sender_display} → {receiver_display} (Хэш: {current_tx_hash or 'N/A'})")
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
                if 'r' in locals() and hasattr(r, 'text'): response_text = r.text
                if response_text: msg += f"\n   Ответ API: {response_text[:300]}"
            results.append(msg)

    if not results:
        return "🐋 Нет данных по крупным транзакциям после всех попыток и фильтрации."
    # Добавляем заголовок к блоку китов
    return "🐋 Крупные транзакции за последние 24 часа (Топ-5 по сетям):\n" + "\n".join(results)