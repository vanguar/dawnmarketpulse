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
    {"name": "Ethereum", "slug": "ethereum", "type": "transfers"},
    {"name": "BSC", "slug": "bsc", "type": "transfers"},
    {"name": "Polygon", "slug": "polygon", "type": "transfers"},
    {"name": "Tron", "slug": "tron", "type": "transfers"},
    {"name": "Solana", "slug": "solana", "type": "transfers", "fallback_amount": 25000},
    {"name": "XRP", "slug": "ripple", "type": "transfers", "fallback_amount": 1000000},
    {"name": "Bitcoin", "slug": "bitcoin", "type": "outputs"}
]

def build_transfer_query(network_slug, date_from, date_to, use_native=False, native_limit=0):
    # Серверная фильтрация по сумме убрана, т.к. API ее не принимал в предыдущих тестах.
    # Фильтрация будет производиться локально.
    # Запрашиваем больше данных (limit: 20) и сортируем на стороне сервера.
    
    order_by_field = "amount" if use_native else "amountUsd"
    
    # ВАЖНО: Убедитесь, что синтаксис limit и orderBy корректен для Bitquery API V2
    # и что указанные поля ('amount', 'amountUsd') действительно доступны для сортировки.
    order_and_limit = f"limit: {{count: 20}}, orderBy: {{descending: \"{order_by_field}\"}}"

    # Прямой запрос к network_slug как корневому полю.
    # ВАЖНО: Для некоторых сетей (особенно EVM) может потребоваться другая структура (например, EVM(network:"slug"){{...}}).
    # Если для каких-то сетей этот запрос не сработает, ищите правильную структуру в документации Bitquery.
    network_specific_query = f"""
    {network_slug} {{
      transfers(
        date: {{since: "{date_from}", till: "{date_to}"}}
        {order_and_limit}
      ) {{
        amount
        amountUsd
        currency {{ symbol }}
        sender {{ address annotation smartContract {{ contractType }} owner }}
        receiver {{ address annotation smartContract {{ contractType }} owner }}
        transaction {{ hash blockTimestamp }}
      }}
    }}
    """
    return {"query": f"{{ {network_specific_query} }}"}

def build_btc_query(date_from, date_to):
    # Серверная фильтрация по сумме (value) убрана.
    # Фильтрация будет производиться локально.

    # ВАЖНО: Убедитесь, что синтаксис limit и orderBy (для поля 'value') корректен.
    order_and_limit = f"limit: {{count: 20}}, orderBy: {{descending: \"value\"}}"
    
    return {
        "query": f"""
{{
  bitcoin {{ # Предполагаем, что "bitcoin" - это правильное корневое поле
    outputs(
      date: {{since: "{date_from}", till: "{date_to}"}}
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
        original_data_from_primary_query = True # Флаг, чтобы знать, откуда данные для фильтрации
        try:
            query = None
            query_fb_func = None # Функция для генерации fallback-запроса

            if net["type"] == "transfers":
                query = build_transfer_query(net["slug"], date_from, date_to, use_native=False)
                if "fallback_amount" in net:
                     query_fb_func = lambda: build_transfer_query(
                        net["slug"], date_from, date_to,
                        use_native=True, # Для fallback используем сортировку по 'amount'
                        native_limit=net["fallback_amount"] # native_limit сейчас не используется для API фильтра
                    )
            elif net["type"] == "outputs": # Bitcoin
                query = build_btc_query(date_from, date_to)
            else:
                results.append(f"⚠️ [{net['name']}] Неподдерживаемый тип данных: {net['type']}.")
                continue

            r = requests.post(BITQUERY_URL, headers=HEADERS, json=query, timeout=45)
            r.raise_for_status()
            data = r.json()

            if "errors" in data:
                error_details = str(data["errors"])
                if query_fb_func:
                    results.append(f"ℹ️ [{net['name']}] Ошибка в основном запросе ({error_details[:100]}), пробую fallback...")
                    original_data_from_primary_query = False # Данные будут из fallback
                    query_fb = query_fb_func()
                    r_fb = requests.post(BITQUERY_URL, headers=HEADERS, json=query_fb, timeout=45)
                    r_fb.raise_for_status()
                    data_fb = r_fb.json()
                    if "errors" in data_fb:
                        error_details_fb = str(data_fb["errors"])
                        results.append(f"❌ [{net['name']}-Fallback] Ошибка API Bitquery: {error_details_fb[:200]}")
                        continue
                    data = data_fb
                    results.append(f"✅ [{net['name']}-Fallback] Данные получены (будут отфильтрованы локально).")
                else:
                    results.append(f"❌ [{net['name']}] Ошибка API Bitquery: {error_details[:200]}")
                    continue
            
            chain_data_root_key = net["slug"] # Общий случай после удаления EVM-обертки
            if net["type"] == "outputs": # Bitcoin имеет свой ключ 'bitcoin'
                chain_data_root_key = "bitcoin"
            
            chain_data_outer = data.get("data", {}).get(chain_data_root_key)

            if chain_data_outer is None:
                results.append(f"ℹ️ [{net['name']}] Нет данных ('{chain_data_root_key}') в ответе Bitquery.")
                continue

            raw_list_from_api = []
            if net["type"] == "transfers":
                raw_list_from_api = chain_data_outer.get("transfers", [])
            elif net["type"] == "outputs":
                raw_list_from_api = chain_data_outer.get("outputs", [])

            if not raw_list_from_api:
                results.append(f"ℹ️ [{net['name']}] API вернул пустой список транзакций/выходов.")
                continue

            # --- Локальная фильтрация ---
            locally_filtered_list = []
            if net["type"] == "transfers":
                USD_FILTER_THRESHOLD = 500000.0
                # Для fallback использовался native_limit для сортировки, но фильтрация все равно по USD, если есть
                # или по native_limit, если amountUsd отсутствует и это был fallback
                NATIVE_FILTER_THRESHOLD_FALLBACK = float(net.get("fallback_amount", 0))

                for tx_item in raw_list_from_api:
                    include_tx = False
                    amount_usd_str = tx_item.get("amountUsd")
                    amount_str = tx_item.get("amount")

                    if amount_usd_str is not None:
                        try:
                            if float(amount_usd_str) >= USD_FILTER_THRESHOLD:
                                include_tx = True
                        except (ValueError, TypeError): pass
                    # Если amountUsd нет или он мал, И это были данные из fallback (где сортировали по amount),
                    # И есть fallback_amount, то проверяем по нему.
                    # Флаг original_data_from_primary_query поможет это определить.
                    elif not original_data_from_primary_query and NATIVE_FILTER_THRESHOLD_FALLBACK > 0 and amount_str is not None:
                         try:
                            if float(amount_str) >= NATIVE_FILTER_THRESHOLD_FALLBACK:
                                include_tx = True
                         except (ValueError, TypeError): pass
                    
                    if include_tx:
                        locally_filtered_list.append(tx_item)

            elif net["type"] == "outputs": # Bitcoin
                BTC_FILTER_THRESHOLD = 10.0
                for tx_item in raw_list_from_api:
                    value_btc_str = tx_item.get("value")
                    if value_btc_str is not None:
                        try:
                            if float(value_btc_str) >= BTC_FILTER_THRESHOLD:
                                locally_filtered_list.append(tx_item)
                        except (ValueError, TypeError): pass
            
            if not locally_filtered_list:
                results.append(f"ℹ️ [{net['name']}] Нет крупных транзакций (после локальной фильтрации).")
                continue
            
            # --- Обработка и вывод отфильтрованных транзакций ---
            count = 0
            for tx_item in locally_filtered_list:
                if count >= 5: break

                tx_hash = tx_item.get("transaction", {}).get("hash")
                if tx_hash and tx_hash in processed_tx_hashes:
                    continue
                
                if net["type"] == "transfers":
                    currency_obj = tx_item.get("currency")
                    if not currency_obj:
                        results.append(f"⚠️ [{net['name']}] Пропуск TX (фильтр): нет данных о валюте. Хэш: {tx_hash or 'N/A'}")
                        continue
                    symbol = currency_obj.get("symbol", "???")

                    # Сумма уже проверена при локальной фильтрации, но для вывода берем ту, что есть
                    amount_to_display_str = tx_item.get("amountUsd") if tx_item.get("amountUsd") is not None else tx_item.get("amount")
                    try:
                        amount_display_float = float(amount_to_display_str) if amount_to_display_str is not None else 0.0
                    except (ValueError, TypeError):
                        amount_display_float = 0.0
                    
                    sender_obj_raw = tx_item.get("sender")
                    receiver_obj_raw = tx_item.get("receiver")

                    if not sender_obj_raw or not receiver_obj_raw: # Доп. проверка, хотя вряд ли нужна после фильтра
                        results.append(f"⚠️ [{net['name']}] Пропуск TX (фильтр): нет отправителя/получателя. Хэш: {tx_hash or 'N/A'}")
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

                    # Определяем, какую сумму выводить и с каким символом
                    display_amount_formatted = f"{amount_display_float:,.0f}"
                    display_symbol = symbol
                    if tx_item.get("amountUsd") is not None: # Если есть сумма в USD, показываем ее
                         # Уже отформатировано выше display_amount_formatted
                         display_symbol = f"USD ({symbol})" if symbol != "???" and float(tx_item.get("amountUsd")) >= USD_FILTER_THRESHOLD else symbol # Уточнение символа
                    elif not original_data_from_primary_query and NATIVE_FILTER_THRESHOLD_FALLBACK > 0 : # Данные из fallback по нативной сумме
                         # display_amount_formatted уже содержит нативную сумму
                         pass # display_symbol остается symbol

                    results.append(f"{direction} [{net['name']}] {display_amount_formatted} {display_symbol}: {sender_display} → {receiver_display}")

                elif net["type"] == "outputs": # Bitcoin
                    value_btc_str = tx_item.get("value") # Уже проверено при фильтрации
                    value_btc = float(value_btc_str) # Должно быть безопасно после фильтра
                    
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
                response_text = None
                if 'r_fb' in locals() and hasattr(r_fb, 'text'): response_text = r_fb.text
                elif 'r' in locals() and hasattr(r, 'text'): response_text = r.text
                if response_text: msg += f"\n   Ответ API: {response_text[:300]}"
            results.append(msg)

    if not results:
        return "🐋 Нет данных по крупным транзакциям после всех попыток и фильтрации." # Изменено сообщение

    return "\n".join(results)