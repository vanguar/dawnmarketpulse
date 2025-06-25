# macro_reader.py  ·  макро-блок для 7 регионов с FRED + World Bank fallback
import os, requests, datetime as dt
from custom_logger import log   # твой штатный логгер

FRED_KEY  = os.getenv("FRED_KEY")
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
WB_BASE   = "https://api.worldbank.org/v2/country"

MONTHS_RU = {1:"янв",2:"фев",3:"мар",4:"апр",5:"май",6:"июн",
             7:"июл",8:"авг",9:"сен",10:"окт",11:"ноя",12:"дек"}

MAX_AGE_DAYS = 180          # ≤ 6 мес
LATEST_ROWS  = 6            # сколько точек вытягиваем из FRED (хватает)

# ───── Словарь серий ──────────────────────────────────────────────────────
SERIES = {
    # Америка, Европа, Япония
    "US": {"flag":"🇺🇸","iso":"usa",
           "cpi_yoy":"CPALTT01USM657N","cpi_idx":None,"wb_cpi":"FP.CPI.TOTL.ZG",
           "ppi":"PPIACO","rate":"FEDFUNDS","unemp":"UNRATE"},
    "EU": {"flag":"🇪🇺","iso":"EMU",
           "cpi_yoy":None,"cpi_idx":"CP0000EZ19M086NEST","wb_cpi":"FP.CPI.TOTL.ZG",
           "ppi":"PRINTO01EZM657N","rate":"ECBDFR","unemp":"LRHUTTTTEZM156S"},
    "JP": {"flag":"🇯🇵","iso":"jpn",
           "cpi_yoy":None,"cpi_idx":"JPNCPIALLMINMEI","wb_cpi":"FP.CPI.TOTL.ZG",
           "ppi":"WPIDEC1JPM661N","rate":"BOJIORBIL","unemp":None},
    # Азия
    "CN": {"flag":"🇨🇳","iso":"chn",
           "cpi_yoy":"CPALTT01CNM657N","cpi_idx":None,"wb_cpi":"FP.CPI.TOTL.ZG",
           "ppi":"WPIDEC1CNM661N","rate":"IRLTLT01CNM156N","unemp":None},
    "KR": {"flag":"🇰🇷","iso":"kor",
           "cpi_yoy":"CPALTT01KRM657N","cpi_idx":None,"wb_cpi":"FP.CPI.TOTL.ZG",
           "ppi":"WPIDEC1KRM661N","rate":"IR3TIB01KRM156N","unemp":None},
    "IN": {"flag":"🇮🇳","iso":"ind",
           "cpi_yoy":"CPALTT01INM657N","cpi_idx":None,"wb_cpi":"FP.CPI.TOTL.ZG",
           "ppi":"WPIDEC1INM661N","rate":"IRLTLT01INM156N","unemp":None},
    "SG": {"flag":"🇸🇬","iso":"sgp",
           "cpi_yoy":"CPALTT01SIM657N","cpi_idx":None,"wb_cpi":"FP.CPI.TOTL.ZG",
           "ppi":None,"rate":None,"unemp":None},
}

# ───── helpers: FRED ───────────────────────────────────────────────────────
def _fred_fetch(sid: str, rows: int = LATEST_ROWS):
    url = (f"{FRED_BASE}?series_id={sid}&api_key={FRED_KEY}"
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

def _fred_latest(sid: str):
    val, d = _first_valid(_fred_fetch(sid))
    if (dt.datetime.today() - dt.datetime.fromisoformat(d)).days > MAX_AGE_DAYS:
        raise ValueError("too old")
    return val, d

def _yoy_from_index(sid: str):
    obs = _fred_fetch(sid, 13)
    latest, _   = _first_valid(obs[:1])
    year_ago, _ = _first_valid(obs[-1:])
    return (latest / year_ago - 1) * 100, obs[0]["date"]

# ───── helpers: World Bank ─────────────────────────────────────────────────
def _wb_latest(country_iso: str, indicator: str):
    url  = f"{WB_BASE}/{country_iso}/indicator/{indicator}?format=json&per_page=1"
    data = requests.get(url, timeout=10).json()[1][0]
    val, year = data["value"], int(data["date"])
    if val is None:
        raise ValueError("WB empty")
    date_iso = f"{year}-07-01"   # середина года
    if (dt.datetime.today() - dt.datetime.fromisoformat(date_iso)).days > MAX_AGE_DAYS:
        raise ValueError("WB too old")
    return float(val), date_iso

def _rus(date_iso: str) -> str:
    d = dt.datetime.fromisoformat(date_iso)
    return f"{MONTHS_RU[d.month]} {d.year}"

# ───── основной блок ──────────────────────────────────────────────────────
def get_macro_block():
    lines = []

    for cfg in SERIES.values():
        flag = cfg["flag"]

        # CPI YoY  (FRED → fallback WB)
        try:
            if cfg["cpi_yoy"]:
                cpi, d_cpi = _fred_latest(cfg["cpi_yoy"])
            else:
                cpi, d_cpi = _yoy_from_index(cfg["cpi_idx"])
        except Exception as e_fred:
            try:
                cpi, d_cpi = _wb_latest(cfg["iso"], cfg["wb_cpi"])
                log(f"ℹ️ CPI {flag} via WB {cpi:.2f} ({d_cpi})")
            except Exception as e_wb:
                log(f"❌ CPI {flag} FRED:{e_fred} WB:{e_wb}")
                continue  # без CPI не показываем страну

        # PPI YoY
        ppi_str = "PPI n/a"
        if cfg["ppi"]:
            try:
                ppi, _ = _yoy_from_index(cfg["ppi"])
                ppi_str = f"PPI {ppi:.1f} %"
            except Exception as e:
                log(f"⚠️ PPI {flag} {e}")

        # Rate
        rate_str = "Rate n/a"
        if cfg["rate"]:
            try:
                rate, _ = _fred_latest(cfg["rate"])
                rate_str = f"Rate {rate:.2f} %"
            except Exception as e:
                log(f"⚠️ RATE {flag} {e}")

        # Unemployment
        unemp_str = ""
        if cfg["unemp"]:
            try:
                unemp, _ = _fred_latest(cfg["unemp"])
                unemp_str = f" | Unemp {unemp:.1f} %"
            except Exception as e:
                log(f"⚠️ UNEMP {flag} {e}")

        lines.append(
            f"{flag} CPI {cpi:.1f} % | {ppi_str} | {rate_str}{unemp_str}  "
            f"({_rus(d_cpi)})"
        )

    if not lines:
        return ""

    header = (
        "📊 Макроэкономика\n"
        "<b>Легенда:</b> CPI — годовая инфляция, "
        "PPI — цены производителей, Rate — ставка ЦБ, Unemp — безработица\n\n"
    )
    return header + "\n".join(lines)
