# macro_reader.py  ·  макро-блок для 7 регионов
import os
import requests
import datetime as dt
from custom_logger import log   # штатный логгер проекта

FRED_KEY = os.getenv("FRED_KEY")
BASE     = "https://api.stlouisfed.org/fred/series/observations"

MONTHS_RU = {
    1:"янв",2:"фев",3:"мар",4:"апр",5:"май",6:"июн",
    7:"июл",8:"авг",9:"сен",10:"окт",11:"ноя",12:"дек"
}

MAX_AGE_DAYS = 180   # берём только релизы моложе 4 месяцев
LATEST_ROWS  = 6     # сколько точек затягиваем за раз

# ——— Series-ID по странам —————————————————————————
SERIES = {
    # Америка, Европа, Япония
    "US": {"flag":"🇺🇸",
           "cpi_yoy":"CPALTT01USM657N", "cpi_idx":None,
           "ppi":"PPIACO",
           "rate":"FEDFUNDS",
           "unemp":"UNRATE"},
    "EU": {"flag":"🇪🇺",
           "cpi_yoy":None,              "cpi_idx":"CP0000EZ19M086NEST",
           "ppi":"PRINTO01EZM657N",
           "rate":"ECBDFR",
           "unemp":"LRHUTTTTEZM156S"},
    "JP": {"flag":"🇯🇵",
           "cpi_yoy":None,              "cpi_idx":"JPNCPIALLMINMEI",
           "ppi":"WPIDEC1JPM661N",
           "rate":"BOJIORBIL",
           "unemp":None},
    # Азия
    "CN": {"flag":"🇨🇳",
           "cpi_yoy":"CPALTT01CNM657N", "cpi_idx":None,
           "ppi":"WPIDEC1CNM661N",
           "rate":"IRLTLT01CNM156N",
           "unemp":None},
    "KR": {"flag":"🇰🇷",
           "cpi_yoy":"CPALTT01KRM657N", "cpi_idx":None,
           "ppi":"WPIDEC1KRM661N",
           "rate":"IR3TIB01KRM156N",
           "unemp":None},
    "IN": {"flag":"🇮🇳",
           "cpi_yoy":"CPALTT01INM657N", "cpi_idx":None,
           "ppi":"WPIDEC1INM661N",
           "rate":"IRLTLT01INM156N",
           "unemp":None},
    "SG": {"flag":"🇸🇬",
           "cpi_yoy":"CPALTT01SIM657N", "cpi_idx":None,
           "ppi":None,
           "rate":None,
           "unemp":None},
}

# ——— helpers ——————————————————————————————————————
def _fetch(sid: str, rows: int = LATEST_ROWS):
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

def _latest(sid: str):
    val, d = _first_valid(_fetch(sid))
    age = (dt.datetime.today() - dt.datetime.fromisoformat(d)).days
    if age > MAX_AGE_DAYS:
        raise ValueError("too old")
    return val, d

def _yoy_from_index(sid: str):
    obs = _fetch(sid, 13)
    latest, _   = _first_valid(obs[:1])
    year_ago, _ = _first_valid(obs[-1:])
    return (latest / year_ago - 1) * 100, obs[0]["date"]

def _rus(date_iso: str) -> str:
    d = dt.datetime.fromisoformat(date_iso)
    return f"{MONTHS_RU[d.month]} {d.year}"

# ——— основной блок ————————————————————————————
def get_macro_block():
    lines = []

    for key, cfg in SERIES.items():
        flag = cfg["flag"]
        try:
            # CPI YoY
            if cfg["cpi_yoy"]:
                cpi, d_cpi = _latest(cfg["cpi_yoy"])
            else:
                cpi, d_cpi = _yoy_from_index(cfg["cpi_idx"])

            # PPI YoY
            ppi_str = "PPI n/a"
            if cfg["ppi"]:
                try:
                    ppi, _ = _yoy_from_index(cfg["ppi"])
                    ppi_str = f"PPI {ppi:.1f} %"
                except Exception as e:
                    log(f"⚠️  PPI {flag} {e}")

            # Rate
            rate_str = "Rate n/a"
            if cfg["rate"]:
                try:
                    rate, _ = _latest(cfg["rate"])
                    rate_str = f"Rate {rate:.2f} %"
                except Exception as e:
                    log(f"⚠️  RATE {flag} {e}")

            # Unemployment
            unemp_str = ""
            if cfg["unemp"]:
                try:
                    unemp, _ = _latest(cfg["unemp"])
                    unemp_str = f" | Unemp {unemp:.1f} %"
                except Exception as e:
                    log(f"⚠️  UNEMP {flag} {e}")

            # собираем строку
            lines.append(
                f"{flag} CPI {cpi:.1f} % | {ppi_str} | {rate_str}{unemp_str}  "
                f"({_rus(d_cpi)})"
            )
        except Exception as e:
            log(f"❌ {flag} {e}")

    return (
        "📊 Макроэкономика (CPI — инфляция г/г, PPI — цены производителей г/г, "
        "Rate — ставка ЦБ, Unemp — безработица)\n" + "\n".join(lines)
    ) if lines else ""
