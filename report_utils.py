"""Utility helpers for GPT-based operations and sentiment analysis.

This module provides:
    * call_gpt – safe wrapper around ``openai.ChatCompletion.create`` with simple retry logic.
    * get_sentiment_description_for_report – helper that converts numeric TextBlob sentiment
      scores into Russian text suitable for Telegram reports.
    * analyze_sentiment – user‑friendly wrapper that returns a formatted sentiment summary.

The sentiment‑related functions are left exactly as before, while the GPT helper has been
re‑added to keep backward compatibility with ``main.py``.
"""

from __future__ import annotations

import os
import time
from datetime import datetime

import openai
from textblob import TextBlob

from custom_logger import log

# ---------------------------------------------------------------------------
# 💬 GPT helper
# ---------------------------------------------------------------------------

MODEL_DEFAULT: str = "gpt-4o-mini"
TIMEOUT: int = 120  # seconds


def call_gpt(
    *,
    system_prompt: str,
    user_content: str = "",
    model: str = MODEL_DEFAULT,
    max_tokens: int = 400,
    temperature: float = 0.4,
    retries: int = 3,
) -> str:
    """Call OpenAI GPT model with automatic retries.

    Args:
        system_prompt: Content for the *system* role.
        user_content: Content for the *user* role.
        model: OpenAI model name (default ``gpt-4o-mini``).
        max_tokens: Max tokens to generate.
        temperature: Sampling temperature.
        retries: How many times to retry on transient API errors.

    Returns:
        Assistant's reply on success, or a stub string if all attempts fail.
    """
    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if user_content:
        messages.append({"role": "user", "content": user_content})

    for attempt in range(retries):
        try:
            resp = openai.ChatCompletion.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=TIMEOUT,
            )
            return resp.choices[0].message.content.strip()
        except openai.error.OpenAIError as exc:
            log(
                f"[call_gpt] attempt {attempt + 1}/{retries} failed: {type(exc).__name__}: {exc}"
            )
            # Exponential backoff: 1s, 2s, 4s, ...
            time.sleep(2 ** attempt)

    return "⚠️ call_gpt: No response from OpenAI after several attempts."


# ---------------------------------------------------------------------------
# 🧠 Sentiment‑analysis helpers (unchanged)
# ---------------------------------------------------------------------------

def get_sentiment_description_for_report(polarity: float, subjectivity: float):
    """Return human‑readable sentiment descriptions for Telegram reports."""
    # Описание полярности (тональности)
    pol_desc_short = "нейтральная"  # По умолчанию
    if polarity > 0.15:
        pol_desc_short = "позитивная"
    elif polarity < -0.15:
        pol_desc_short = "негативная"

    # Описание стиля изложения (субъективности)
    sub_style_desc = "объективный стиль"  # По умолчанию
    comment_text = (
        "Текст построен на фактах и данных, не содержит ярко выраженной эмоциональной оценки или личных мнений."
    )

    if subjectivity > 0.75:  # Очень субъективный
        sub_style_desc = "очень субъективный стиль"
        comment_text = (
            "Текст содержит значительное количество личных мнений, предположений или эмоциональных выражений, отходя от чисто фактического изложения."
        )
    elif subjectivity > 0.45:  # Умеренно субъективный
        sub_style_desc = "умеренно субъективный стиль"
        comment_text = (
            "В тексте присутствуют элементы личной оценки, мнений или интерпретаций наряду с фактической информацией."
        )

    return pol_desc_short, sub_style_desc, comment_text


def analyze_sentiment(text_to_analyze: str) -> str:
    """Analyze sentiment of *text_to_analyze* and return a nicely formatted summary."""
    if not isinstance(text_to_analyze, str) or not text_to_analyze.strip():
        return (
            "🧠 Анализ тональности текста GPT:\n        • Ошибка: Текст для анализа не предоставлен или пуст."
        )

    try:
        blob = TextBlob(text_to_analyze)
        polarity = blob.sentiment.polarity
        subjectivity = blob.sentiment.subjectivity

        pol_desc_short, sub_style_desc, comment_text = get_sentiment_description_for_report(
            polarity, subjectivity
        )

        tone_emoji = "📊"  # Нейтральное по умолчанию
        if polarity > 0.15:
            tone_emoji = "📈"  # Позитивное
        elif polarity < -0.15:
            tone_emoji = "📉"  # Негативное

        return (
            f"🧠 Анализ тональности текста GPT:\n\n"
            f"{tone_emoji} Тональность: {pol_desc_short} (числовое значение: {polarity:.2f})\n"
            f"🧐 Стиль изложения: {sub_style_desc} (числовое значение: {subjectivity:.2f})\n\n"
            f"💬 Комментарий от GPT-Аналитика: {comment_text}"
        )

    except Exception as exc:  # pylint: disable=broad-except
        log(f"[analyze_sentiment] error: {type(exc).__name__}: {exc}")
        return (
            "🧠 Анализ тональности текста GPT:\n        • Произошла ошибка при попытке анализа тональности."
        )

# ---------------------------------------------------------------------------
# End of file
# -------------------------------------------------------------------------