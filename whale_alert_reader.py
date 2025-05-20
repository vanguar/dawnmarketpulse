import os
import requests
from datetime import datetime, timedelta

BITQUERY_TOKEN = os.getenv("BITQUERY_TOKEN")
BITQUERY_URL = "https://graphql.bitquery.io/" # Этот URL уже правильный

HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {BITQUERY_TOKEN}"
}

NETWORKS = [
    {"name": "Ethereum", "slug": "ethereum", "type": "transfers_evm"}, # Тип изменен для EVM
    {"name": "BSC", "slug": "bsc", "type": "transfers_evm"},          # Тип изменен для EVM
    {"name": "Polygon", "slug": "polygon", "type": "transfers_evm"},  # Тип изменен для EVM
    {"name": "Tron", "slug": "tron", "type": "transfers_direct"}, # Предполагаем прямой доступ, НУЖНО ПРОВЕРИТЬ ДОКУМЕНТАЦИЮ!
    {"name": "Solana", "slug": "solana", "type": "transfers_direct"},# Предполагаем прямой доступ, НУЖНО ПРОВЕРИТЬ ДОКУМЕНТАЦИЮ!
    {"name": "XRP", "slug": "ripple", "type": "transfers_direct"}, # Предполагаем прямой доступ, НУЖНО ПРОВЕРИТЬ ДОКУМЕНТАЦИЮ!
    {"name": "Bitcoin", "slug": "bitcoin", "type": "outputs"}
]

def build_transfer_query(network_slug, type, date_from, date_to, use_native=False, native_limit=0):
    # Формируем фильтр для 'where'
    # Числовые значения передаем как строки согласно документации Bitquery
    if use_native:
        inner_filter_content = f"amount: {{gt: \"{native_limit}\"}}"
        order_by_field = "amount" # Поле для сортировки в fallback
    else:
        inner_filter_content = f"amountUsd: {{gt: \"500000\"}}"
        order_by_field = "amountUsd" # Основное поле для сортировки

    # Структура where: { field: { operator: "value" } }
    where_clause = f"where: {{ {inner_filter_content} }}"

    # Сортировка и лимит согласно примерам из документации Bitquery (limit: {count: N}, orderBy: {descending: "FieldName"})
    # ВАЖНО: Убедитесь, что "amountUsd" и "amount" являются корректными полями для сортировки в схеме Bitquery.
    order_and_limit = f"limit: {{count: 10}}, orderBy: {{descending: \"{order_by_field}\"}}"

    common_transfers_body = f"""
    transfers(
      date: {{since: "{date_from}", till: "{date_to}"}}
      {where_clause}
      {order_and_limit}
    ) {{
      amount
      amountUsd
      currency {{ symbol }}
      sender {{ address annotation smartContract {{ contractType }} owner }}
      receiver {{ address annotation smartContract {{ contractType }} owner }}
      transaction {{ hash blockTimestamp }}
    }}
    """

    if type == "transfers_evm":
        # Для EVM сетей запрос оборачивается в EVM(network: "slug")
        network_specific_query = f"EVM(network: \"{network_slug}\") {{ {common_transfers_body} }}"
    elif type == "transfers_direct":
        # Для сетей, где slug может быть корневым полем (ТРЕБУЕТ ПРОВЕРКИ ПО ДОКУМЕНТАЦИИ!)
        network_specific_query = f"{network_slug} {{ {common_transfers_body} }}"
    else:
        raise ValueError(f"Неизвестный тип сети для transfer query: {type}")
        
    return {"query": f"{{ {network_specific_query} }}"}

def build_btc_query(date_from, date_to):
    # Фильтр по value внутри 'where' и значение как строка
    where_clause = f"where: {{ value: {{gt: \"10\"}} }}" # gt: "10" для Bitcoin value
    
    # Сортировка и лимит
    # ВАЖНО: Убедитесь, что "value" является корректным полем для сортировки в схеме Bitquery.
    order_and_limit = f"limit: {{count: 10}}, orderBy: {{descending: \"value\"}}"
    
    return {
        "query": f"""
{{
  bitcoin {{ # Предполагаем, что "bitcoin" - это правильное корневое поле
    outputs(
      date: {{since: "{date_from}", till: "{date_to}"}}
      {where_clause}
      {order_and_limit}
    ) {{
      value
      address {{ address annotation owner }} # Get output address and its annotations
      transaction {{
        hash
        blockTimestamp
        inputs(options: {{limit:50}}) {{ address {{address annotation owner}} }} # Get input addresses
        outputs(options: {{limit:50}}) {{ address {{address annotation owner}} }} # And all outputs for change analysis
      }}
    }}
  }}
}}"""}

def get_display_name(addr_obj):
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

    processed_tx_hashes = set()

    for net in NETWORKS:
        try:
            query = None
            if net["type"] == "transfers_evm" or net["type"] == "transfers_direct":
                query = build_transfer_query(net["slug"], net["type"], date_from, date_to)
                if "fallback_amount" in net: # Сохраняем возможность fallback
                     query_fb_func = lambda: build_transfer_query(
                        net["slug"], net["type"], date_from, date_to,
                        use_native=True,
                        native_limit=net["fallback_amount"]
                    )
                else:
                    query_fb_func = None

            elif net["type"] == "outputs": # Bitcoin
                query = build_btc_query(date_from, date_to)
                query_fb_func = None # Нет fallback для Bitcoin в текущей логике
            else:
                results.append(f"⚠️ [{net['name']}] Неподдерживаемый тип данных: {net['type']}.")
                continue

            r = requests.post(BITQUERY_URL, headers=HEADERS, json=query, timeout=45)
            r.raise_for_status()
            data = r.json()

            if "errors" in data:
                error_details = str(data["errors"])
                # Если есть fallback и основная ошибка, пытаемся сделать fallback
                if query_fb_func:
                    results.append(f"ℹ️ [{net['name']}] Ошибка в основном запросе ({error_details[:100]}), пробую fallback...")
                    query_fb = query_fb_func()
                    r_fb = requests.post(BITQUERY_URL, headers=HEADERS, json=query_fb, timeout=45)
                    r_fb.raise_for_status()
                    data_fb = r_fb.json()
                    if "errors" in data_fb:
                        error_details_fb = str(data_fb["errors"])
                        results.append(f"❌ [{net['name']}-Fallback] Ошибка API Bitquery: {error_details_fb[:200]}")
                        continue
                    data = data_fb # Используем данные из fallback
                    results.append(f"✅ [{net['name']}-Fallback] Данные получены.")
                else:
                    results.append(f"❌ [{net['name']}] Ошибка API Bitquery: {error_details[:200]}")
                    continue
            
            # Определяем ключ для извлечения данных (EVM или прямой slug)
            if net["type"] == "transfers_evm":
                chain_data_outer = data.get("data", {}).get("EVM")
            elif net["type"] == "transfers_direct":
                 chain_data_outer = data.get("data", {}).get(net["slug"])
            elif net["type"] == "outputs": # Bitcoin
                chain_data_outer = data.get("data", {}).get("bitcoin")
            else:
                chain_data_outer = None

            if chain_data_outer is None:
                data_key_name = f"EVM/{net['slug']}" if net["type"] == "transfers_evm" else net["slug"]
                results.append(f"ℹ️ [{net['name']}] Нет данных ('{data_key_name}') в ответе Bitquery после обработки.")
                continue

            # Извлекаем список транзакций/выходов
            if net["type"] == "transfers_evm" or net["type"] == "transfers_direct":
                transfers_list = chain_data_outer.get("transfers", [])
            elif net["type"] == "outputs":
                transfers_list = chain_data_outer.get("outputs", [])
            else:
                transfers_list = []


            if not transfers_list:
                # Если основной запрос не дал результатов, а fallback не был задействован из-за отсутствия ошибок,
                # но должен был быть (т.е. transfers_list пуст, но fallback_amount есть),
                # то это условие не совсем корректно обработает ситуацию "пустой ответ, но есть fallback"
                # Логика fallback выше уже должна была это покрыть, если был error.
                # Если просто пустой список без ошибок, то fallback по текущей логике не вызывается,
                # кроме как через 'use_native=True' в query_fb_func.
                # Это условие оставлено для случая, если даже fallback вернул пустой список.
                if query_fb_func and not data.get("errors"): # Если fallback был, но все равно пусто
                     results.append(f"ℹ️ [{net['name']}] Нет крупных транзакций (включая fallback).")
                else: # Если fallback не было или он тоже не дал
                     results.append(f"ℹ️ [{net['name']}] Нет крупных транзакций.")
                continue
            
            count = 0
            for tx_item in transfers_list: # tx_item это либо transfer, либо output
                if count >= 5: break

                tx_hash = tx_item.get("transaction", {}).get("hash")
                if tx_hash and tx_hash in processed_tx_hashes:
                    continue
                
                if net["type"] == "transfers_evm" or net["type"] == "transfers_direct":
                    currency_obj = tx_item.get("currency")
                    if not currency_obj:
                        results.append(f"⚠️ [{net['name']}] Пропуск TX: нет данных о валюте. Хэш: {tx_hash or 'N/A'}")
                        continue
                    symbol = currency_obj.get("symbol", "???")

                    amount_val = tx_item.get("amount")
                    try:
                        amount_float = float(amount_val) if amount_val is not None else 0.0
                    except (ValueError, TypeError):
                        results.append(f"⚠️ [{net['name']}] Пропуск TX: неверный формат суммы '{amount_val}'. Хэш: {tx_hash or 'N/A'}")
                        continue
                    
                    if amount_float == 0.0 and not tx_item.get("amountUsd"):
                        continue

                    sender_obj_raw = tx_item.get("sender")
                    receiver_obj_raw = tx_item.get("receiver")

                    if not sender_obj_raw or not receiver_obj_raw:
                        results.append(f"⚠️ [{net['name']}] Пропуск TX: нет данных об отправителе/получателе. Хэш: {tx_hash or 'N/A'}")
                        continue
                    
                    sender_display = get_display_name(sender_obj_raw)
                    receiver_display = get_display_name(receiver_obj_raw)
                    
                    direction = "🔁"
                    if sender_obj_raw.get("owner") or ("exchange" in str(sender_obj_raw.get("annotation","")).lower()):
                         if not (receiver_obj_raw.get("owner") or ("exchange" in str(receiver_obj_raw.get("annotation","")).lower())):
                            direction = "💸 Вывод" 
                    elif receiver_obj_raw.get("owner") or ("exchange" in str(receiver_obj_raw.get("annotation","")).lower()):
                        if not (sender_obj_raw.get("owner") or ("exchange" in str(sender_obj_raw.get("annotation","")).lower())):
                            direction = "🐳 Ввод"

                    results.append(f"{direction} [{net['name']}] {amount_float:,.0f} {symbol}: {sender_display} → {receiver_display}")

                elif net["type"] == "outputs": # Bitcoin (btc_out это tx_item)
                    value_btc_str = tx_item.get("value")
                    try:
                        value_btc = float(value_btc_str) if value_btc_str is not None else 0.0
                    except (ValueError, TypeError):
                        results.append(f"⚠️ [Bitcoin] Пропуск Output: неверный формат value '{value_btc_str}'. Хэш: {tx_hash or 'N/A'}")
                        continue
                    if value_btc == 0.0: continue
                    
                    tx_detail_obj = tx_item.get("transaction")
                    output_address_obj = tx_item.get("address")

                    sender_display = "Несколько входов"
                    receiver_display = get_display_name(output_address_obj)

                    if tx_detail_obj:
                        inputs = tx_detail_obj.get("inputs", [])
                        if inputs:
                            first_input_addr_obj = inputs[0].get("address")
                            if first_input_addr_obj and output_address_obj and first_input_addr_obj.get("address") != output_address_obj.get("address"):
                                sender_display_candidate = get_display_name(first_input_addr_obj)
                                if sender_display_candidate != receiver_display or receiver_display == "???":
                                     sender_display = sender_display_candidate
                    results.append(f"💸 [Bitcoin] ~{value_btc:.2f} BTC: {sender_display} → {receiver_display} (Хэш: {tx_hash or 'N/A'})")

                if tx_hash: processed_tx_hashes.add(tx_hash)
                count += 1

        except requests.exceptions.HTTPError as http_err:
            results.append(f"⚠️ [{net['name']}] HTTP ошибка: {http_err.response.status_code} - {http_err.response.text[:100]}")
        except requests.exceptions.Timeout:
            results.append(f"⚠️ [{net['name']}] Таймаут запроса к Bitquery.")
        except requests.exceptions.RequestException as req_err:
            results.append(f"⚠️ [{net['name']}] Сетевая ошибка: {req_err}")
        except Exception as e:
            msg = f"⚠️ [{net['name']}] Общая ошибка: {str(e)}"
            if debug:
                # Безопасная проверка наличия r или r_fb и их атрибута text
                response_text = None
                if 'r_fb' in locals() and hasattr(r_fb, 'text'): response_text = r_fb.text
                elif 'r' in locals() and hasattr(r, 'text'): response_text = r.text
                if response_text: msg += f"\n   Ответ API: {response_text[:300]}"
            results.append(msg)

    if not results:
        return "🐋 Нет значимых транзакций китов за последние 24 часа."

    return "\n".join(results)