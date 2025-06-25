# macro_reader.py
import os
import requests
import datetime as dt
from custom_logger import log               # твой штатный логгер

FRED_KEY = os.getenv("FRED_KEY")
BASE = "https://api.stlouisfed.org/fred/series/observations"

# ——— русские сокращения месяцев
MONTHS_RU = {
    1: "янв", 2: "фев", 3: "мар", 4: "апр", 5: "май", 6: "июн",
    7: "июл", 8: "авг", 9: "сен", 10: "окт", 11: "ноя", 12: "дек"
}

# ——— Series-ID
SERIES = {
    "US": {
        "flag":  "🇺🇸",
        "cpi":   "CPALTT01USM657N",      # CPI YoY %
        "ppi":   "PPIACO",               # PPI index ‒ посчитаем YoY
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
        "unemp": None,
    },
}

MAX_AGE_DAYS = 800       # допустимый лаг ~26 мес

# ——— helpers --------------------------------------------------------------
def _fetch(series_id: str, rows: int = 13):
    url = (
        f"{BASE}?series_id={series_id}&api_key={FRED_KEY}"
        f"&file_type=json&sort_order=desc&limit={rows}"
    )
    data = requests.get(url, timeout=10).json()
    if "observations" not in data:
        err = data.get("error_message", data)
        raise ValueError(f"FRED error: {err}")
    return data["observations"]


def _to_float(val: str) -> float:
    if val in ("", "."):
        raise ValueError("missing value")
    return float(val)


def _latest(series_id: str):
    """
    Возвращает (value, date_iso) — берёт ближайшее ненулевое наблюдение,
    проверяет давность.
    """
    for obs in _fetch(series_id):
        try:
            value = _to_float(obs["value"])
            date_iso = obs["date"]
            break
        except ValueError:
            continue
    else:
        raise ValueError("all recent values empty")

    if (dt.datetime.today() - dt.datetime.fromisoformat(date_iso)).days > MAX_AGE_DAYS:
        raise ValueError("data too old")
    return value, date_iso


def _ppi_yoy(series_id: str):
    """PPI YoY (%) — (последнее / год_назад − 1) × 100"""
    obs = _fetch(series_id, 13)
    latest = _to_float(obs[0]["value"])
    year_ago = _to_float(obs[-1]["value"])
    yoy = (latest / year_ago - 1) * 100
    return yoy, obs[0]["date"]


def _rus_date(iso: str) -> str:
    d = dt.datetime.fromisoformat(iso)
    return f"{MONTHS_RU[d.month]} {d.year}"

# ——— safe-wrappers для подробного лога -----------------------------------
def safe_latest(label: str, sid: str):
    try:
        val, d = _latest(sid)
        log(f"✅ {label}: {val}  ({d})")
        return val, d
    except Exception as e:
        log(f"❌ {label} ERROR: {e}")
        raise


def safe_ppi(label: str, sid: str):
    try:
        val, d = _ppi_yoy(sid)
        log(f"✅ {label}: {val:.2f}%  ({d})")
        return val, d
    except Exception as e:
        log(f"❌ {label} ERROR: {e}")
        raise

# ——— main -----------------------------------------------------------------
def get_macro_block() -> str:
    lines = []

    for country, data in SERIES.items():
        flag = data["flag"]

        # CPI — обязателен
        try:
            cpi, date_cpi = safe_latest(f"CPI {flag}", data["cpi"])
        except Exception:
            continue

        # PPI YoY
        try:
            ppi, _ = safe_ppi(f"PPI {flag}", data["ppi"])
            ppi_part = f"PPI {ppi:.1f} %"
        except Exception:
            ppi_part = "PPI n/a"

        # Rate
        try:
            rate, _ = safe_latest(f"RATE {flag}", data["rate"])
            rate_part = f"Rate {rate:.2f} %"
        except Exception:
            rate_part = "Rate n/a"

        # Unemp
        unemp_part = ""
        if data["unemp"]:
            try:
                unemp, _ = safe_latest(f"UNEMP {flag}", data["unemp"])
                unemp_part = f" | Unemp {unemp:.1f} %"
            except Exception:
                pass

        lines.append(
            f"{flag} CPI {cpi:.1f} % | {ppi_part} | {rate_part}{unemp_part}  "
            f"({_rus_date(date_cpi)})"
        )

    return (
        "📊 Макроэкономика (CPI — инфляция г/г, PPI — цены производителей г/г, "
        "Rate — ставка ЦБ, Unemp — безработица)\n" + "\n".join(lines)
    ) if lines else ""
