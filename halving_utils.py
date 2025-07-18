#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""halving_utils.py
Утилиты для вычисления обратного отсчёта до следующего халвинга Биткоина.

Функция `get_btc_halving_countdown_line()` возвращает готовую строку на русском языке,
которую можно напрямую вставлять в Telegram‑сообщение бота.
"""

from __future__ import annotations

import requests
from datetime import datetime, timezone

# ── ПАРАМЕТРЫ ХАЛВИНГА ─────────────────────────────────────────────────────────
# Высота блока, на которой произойдёт пятый халвинг (примерно апрель 2028).
NEXT_HALVING_HEIGHT: int = 1_050_000
# Среднее время генерации блока в минутах. Можно уточнять при необходимости.
AVG_BLOCK_TIME_MIN: float = 9.5

# URL Blockstream REST‑API, возвращает текущий height как plain‑text.
BLOCKSTREAM_HEIGHT_URL: str = "https://blockstream.info/api/blocks/tip/height"


# ── ВНУТРЕННИЕ ФУНКЦИИ ─────────────────────────────────────────────────────────

def _get_current_height(timeout: int = 8) -> int:
    """Запрашивает у Blockstream API текущий номер блока.
    Возвращает целое число. При ошибке поднимает исключение requests.*"""
    resp = requests.get(BLOCKSTREAM_HEIGHT_URL, timeout=timeout)
    resp.raise_for_status()
    return int(resp.text.strip())


# ── ЭКСПОРТ ─────────────────────────────────────────────────────────────────────

def get_btc_halving_countdown_line() -> str:
    """Возвращает строку вида:

    ⏳ До халвинга Биткоина осталось 1023 дн.
    Награда за блок при этом уменьшится с 3,125 до 1,5625 BTC.

    Если запрос к API не удался, возвращается строка‑сообщение об ошибке.
    """
    try:
        height = _get_current_height()
        # Сколько блоков осталось добыть до события.
        blocks_left = max(0, NEXT_HALVING_HEIGHT - height)

        # Переводим в минуты → дни (60 * 24 = 1440 минут в сутках).
        minutes_left = blocks_left * AVG_BLOCK_TIME_MIN
        days_left = round(minutes_left / 1440)

        return (
            f"⏳ До халвинга Биткоина осталось {days_left} дн.\n"
            "Награда за блок при этом уменьшится с 3,125 до 1,5625 BTC."
        )

    except Exception as exc:  # Перехватываем любые ошибки.
        return f"⏳ Ошибка счётчика халвинга: {type(exc).__name__} – {exc}"
