# macro_reader.py
import os, requests, datetime as dt
from custom_logger import log

FRED_KEY = os.getenv("FRED_KEY")
BASE = "https://api.stlouisfed.org/fred/series/observations"

MONTHS_RU = {1:"янв",2:"фев",3:"мар",4:"апр",5:"май",6:"июн",
             7:"июл",8:"авг",9:"сен",10:"окт",11:"ноя",12:"дек"}

MAX_AGE_DAYS = 120   # ≤ 4 мес

SERIES = {
    "US": {
        "flag":  "🇺🇸",
        "cpi_yoy": "CPALTT01USM657N",     # готовая YoY
        "cpi_idx": None,                  # не нужен
        "ppi":   "PPIACO",
        "rate":  "FEDFUNDS",
        "unemp": "UNRATE",
    },
    "EU": {
        "flag":  "🇪🇺",
        "cpi_yoy": None,                  # YoY нет → считаем сами
        "cpi_idx": "CP0000EZ19M086NEST",  # индекс HICP
        "ppi":   "PRINTO01EZM661S",
        "rate":  "ECBDFR",
        "unemp": "LRHUTTTTEZM156S",
    },
    "JP": {
        "flag":  "🇯🇵",
        "cpi_yoy": None,
        "cpi_idx": "JPNCPIALLMINMEI",     # индекс CPI JP
        "ppi":   "WPIDEC1JPM661N",
        "rate":  "BOJIORBIL",
        "unemp": None,
    },
}

# ─ helpers ────────────────────────────────────────────────────────────────
def _fetch(sid, rows=13):
    url = (f"{BASE}?series_id={sid}&api_key={FRED_KEY}"
           f"&file_type=json&sort_order=desc&limit={rows}")
    data = requests.get(url, timeout=10).json()
    if "observations" not in data:
        raise ValueError(data.get("error_message", "no observations"))
    return data["observations"]

def _first_valid(obs):
    for o in obs:
        if o["value"] not in ("", "."):
            return float(o["value"]), o["date"]
    raise ValueError("empty values")

def _latest(sid):
    val, d = _first_valid(_fetch(sid, 3))
    if (dt.datetime.today() - dt.datetime.fromisoformat(d)).days > MAX_AGE_DAYS:
        raise ValueError("too old")
    return val, d

def _yoy_from_index(sid):
    obs = _fetch(sid, 13)
    new, _  = _first_valid(obs[:1])
    old, d0 = _first_valid(obs[-1:])
    return (new / old - 1) * 100, obs[0]["date"]

def _ppi_yoy(sid):
    return _yoy_from_index(sid)

def _rus(d): 
    dt_ = dt.datetime.fromisoformat(d)
    return f"{MONTHS_RU[dt_.month]} {dt_.year}"

# ─ safe-wrappers для логов ────────────────────────────────────────────────
def safe(func, label, *args):
    try:
        val, d = func(*args)
        log(f"✅ {label}: {val}  ({d})")
        return val, d
    except Exception as e:
        log(f"❌ {label} ERROR: {e}")
        raise

# ─ main блок ─────────────────────────────────────────────────────────────
def get_macro_block():
    lines = []

    for cfg in SERIES.values():
        flag = cfg["flag"]

        # CPI YoY
        try:
            if cfg["cpi_yoy"]:
                cpi, d_cpi = safe(_latest, f"CPI {flag}", cfg["cpi_yoy"])
            else:
                cpi, d_cpi = safe(_yoy_from_index, f"CPI {flag}", cfg["cpi_idx"])
        except Exception:
            continue   # без CPI не выводим страну

        # PPI YoY
        try:
            ppi, _ = safe(_ppi_yoy, f"PPI {flag}", cfg["ppi"])
            ppi_part = f"PPI {ppi:.1f} %"
        except Exception:
            ppi_part = "PPI n/a"

        # Rate
        try:
            rate, _ = safe(_latest, f"RATE {flag}", cfg["rate"])
            rate_part = f"Rate {rate:.2f} %"
        except Exception:
            rate_part = "Rate n/a"

        # Unemployment
        unemp_part = ""
        if cfg["unemp"]:
            try:
                unemp, _ = safe(_latest, f"UNEMP {flag}", cfg["unemp"])
                unemp_part = f" | Unemp {unemp:.1f} %"
            except Exception:
                pass

        lines.append(
            f"{flag} CPI {cpi:.1f} % | {ppi_part} | {rate_part}{unemp_part}  "
            f"({_rus(d_cpi)})"
        )

    return (
        "📊 Макроэкономика (CPI — инфляция г/г, PPI — цены производителей г/г, "
        "Rate — ставка ЦБ, Unemp — безработица)\n" + "\n".join(lines)
    ) if lines else ""
