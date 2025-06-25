# macro_reader.py
import os
import requests
import datetime as dt

FRED_KEY = os.getenv("FRED_KEY")
BASE = "https://api.stlouisfed.org/fred/series/observations"

# русские сокращения месяцев
MONTHS_RU = {
    1: "янв", 2: "фев", 3: "мар", 4: "апр", 5: "май", 6: "июн",
    7: "июл", 8: "авг", 9: "сен", 10: "окт", 11: "ноя", 12: "дек"
}

# Series-ID для каждой страны
SERIES = {
    "US": {
        "flag":  "🇺🇸",
        "cpi":   "CPALTT01USM657N",      # CPI YoY %
        "ppi":   "PPIACO",               # PPI index — посчитаем YoY
        "rate":  "FEDFUNDS",             # ставка ФРС %
        "unemp": "UNRATE",
    },
    "EU": {
        "flag":  "🇪🇺",
        "cpi":   "CPALTT01EZM657N",
        "ppi":   "PRINTO01EZM661S",      # PPI index (ЕС)
        "rate":  "ECBDFR",               # ставка ЕЦБ %
        "unemp": "LRHUTTTTEZM156S",
    },
    "JP": {
        "flag":  "🇯🇵",
        "cpi":   "CPALTT01JPM657N",
        "ppi":   "WPIDEC1JPM661N",       # PPI index (Япония)
        "rate":  "IRSTCB01JPM156N",      # ставка BoJ %
        "unemp": None,                   # безработица пока пропускаем
    },
}

MAX_AGE_DAYS = 400    # игнорируем серии старше 13 месяцев


# ────────────────────── helpers ──────────────────────
def _fetch(series_id: str, limit: int = 1):
    url = (
        f"{BASE}?series_id={series_id}&api_key={FRED_KEY}"
        f"&file_type=json&sort_order=desc&limit={limit}"
    )
    return requests.get(url, timeout=10).json()["observations"]


def _latest(series_id: str):
    """возвращает (value, date_iso) последнего релиза; фильтрует устаревшее"""
    obs = _fetch(series_id, 1)[0]
    date_iso = obs["date"]
    if (dt.datetime.today() - dt.datetime.fromisoformat(date_iso)).days > MAX_AGE_DAYS:
        raise ValueError("data too old")
    return float(obs["value"]), date_iso


def _ppi_yoy(series_id: str):
    """вычисляет год-к-году (%), беря последний пункт и пункт год назад"""
    obs = _fetch(series_id, 13)               # берём 13 месяцев, чтобы хватило
    latest, prev_year = float(obs[0]["value"]), float(obs[-1]["value"])
    date_iso = obs[0]["date"]
    if any(v in ("", ".") for v in (latest, prev_year)):
        raise ValueError("missing PPI data")
    yoy = (latest / prev_year - 1) * 100
    return yoy, date_iso


def _rus_date(date_iso: str) -> str:
    d = dt.datetime.fromisoformat(date_iso)
    return f"{MONTHS_RU[d.month]} {d.year}"


# ────────────────────── public ──────────────────────
def get_macro_block() -> str:
    lines = []

    for data in SERIES.values():
        flag = data["flag"]

        # CPI
        try:
            cpi, date_cpi = _latest(data["cpi"])
        except Exception:
            continue  # без CPI страну не выводим

        # PPI YoY
        try:
            ppi, _ = _ppi_yoy(data["ppi"])
            ppi_part = f"PPI {ppi:.1f} %"
        except Exception:
            ppi_part = "PPI n/a"

        # Rate
        try:
            rate, _ = _latest(data["rate"])
            rate_part = f"Rate {rate:.2f} %"
        except Exception:
            rate_part = "Rate n/a"

        # Unemployment (не критично)
        unemp_part = ""
        if data["unemp"]:
            try:
                unemp, _ = _latest(data["unemp"])
                unemp_part = f" | Unemp {unemp:.1f} %"
            except Exception:
                pass

        lines.append(
            f"{flag} CPI {cpi:.1f} % | {ppi_part} | {rate_part}{unemp_part}  "
            f"({_rus_date(date_cpi)})"
        )

    return (
        "📊 Макроэкономика (CPI — инфляция г/г, PPI — цены производителей г/г, "
        "Rate — ставка ЦБ, Unemp — безработица)\n"
        + "\n".join(lines)
    ) if lines else ""
