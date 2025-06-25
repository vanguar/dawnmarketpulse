# macro_reader.py – 7 регионов, FRED+WorldBank, значок 🕒 для “старых” данных
import os, requests, datetime as dt
from custom_logger import log

FRED_KEY  = os.getenv("FRED_KEY")
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
WB_BASE   = "https://api.worldbank.org/v2/country"

MONTHS_RU = {1:"янв",2:"фев",3:"мар",4:"апр",5:"май",6:"июн",
             7:"июл",8:"авг",9:"сен",10:"окт",11:"ноя",12:"дек"}

MAX_AGE_DAYS      = 365      # ≤ 12 мес
STALE_BADGE_DAYS  = 210      # > 7 мес → 🕒
LATEST_ROWS       = 15       # глубже копаем FRED

SERIES = {
    "US": {"flag":"🇺🇸","iso":"usa",
           "cpi_yoy":None,"cpi_idx":"CPIAUCSL","wb_cpi":"FP.CPI.TOTL.ZG",
           "ppi":"PPIACO",
           "rate":"FEDFUNDS",
           "unemp":"UNRATE"},
    "EU": {"flag":"🇪🇺","iso":"EMU",
           "cpi_yoy":None,"cpi_idx":"CP0000EZ19M086NEST","wb_cpi":"FP.CPI.TOTL.ZG",
           "ppi":"PRINTO01EZM661N",           ### исправлено
           "rate":"ECBDFR",
           "unemp":"LRHUTTTTEZM156S"},
    "JP": {"flag":"🇯🇵","iso":"jpn",
           "cpi_yoy":None,"cpi_idx":"JPNCPIALLMINMEI","wb_cpi":"FP.CPI.TOTL.ZG",
           "ppi":"WPIDEC1JPM661N",
           "rate":"IRSTCI01JPM156N",          ### исправлено
           "unemp":None},
    # — Азия
    "CN": {"flag":"🇨🇳","iso":"chn",
           "cpi_yoy":"CPALTT01CNM657N","cpi_idx":None,"wb_cpi":"FP.CPI.TOTL.ZG",
           "ppi":None,                        ### нет → n/a
           "rate":None,
           "unemp":None},
    "KR": {"flag":"🇰🇷","iso":"kor",
           "cpi_yoy":"CPALTT01KRM657N","cpi_idx":None,"wb_cpi":"FP.CPI.TOTL.ZG",
           "ppi":None,                        ### нет → n/a
           "rate":None,
           "unemp":None},
    "IN": {"flag":"🇮🇳","iso":"ind",
           "cpi_yoy":"CPALTT01INM657N","cpi_idx":None,"wb_cpi":"FP.CPI.TOTL.ZG",
           "ppi":None,                        ### нет → n/a
           "rate":None,
           "unemp":None},
    "SG": {"flag":"🇸🇬","iso":"sgp",
           "cpi_yoy":"CPALTT01SIM657N","cpi_idx":None,"wb_cpi":"FP.CPI.TOTL.ZG",
           "ppi":None,
           "rate":None,
           "unemp":None},
}

# ---- helpers: FRED -------------------------------------------------------
def _fred_fetch(sid, rows=LATEST_ROWS):
    url=(f"{FRED_BASE}?series_id={sid}&api_key={FRED_KEY}"
         f"&file_type=json&sort_order=desc&limit={rows}")
    data=requests.get(url,timeout=10).json()
    if "observations" not in data:
        raise ValueError(data.get("error_message","no obs"))
    return data["observations"]

def _first_valid(obs):
    for o in obs:
        if o["value"] not in ("","."):
            return float(o["value"]),o["date"]
    raise ValueError("empty")

def _fred_latest(sid):
    val,d=_first_valid(_fred_fetch(sid))
    age=(dt.datetime.today()-dt.datetime.fromisoformat(d)).days
    if age>MAX_AGE_DAYS: raise ValueError("too old")
    return val,d,age

def _yoy_from_index(sid):
    obs=_fred_fetch(sid,13)
    new,_=_first_valid(obs[:1])
    old,_=_first_valid(obs[-1:])
    return (new/old-1)*100,obs[0]["date"]

# ---- helpers: World Bank -------------------------------------------------
def _wb_latest(iso,ind):
    url=f"{WB_BASE}/{iso}/indicator/{ind}?format=json&per_page=1"
    data=requests.get(url,timeout=10).json()[1][0]
    val,year=data["value"],int(data["date"])
    if val is None: raise ValueError("WB empty")
    d=f"{year}-07-01"
    age=(dt.datetime.today()-dt.datetime.fromisoformat(d)).days
    if age>MAX_AGE_DAYS: raise ValueError("WB too old")
    return float(val),d,age

def _rus(d_iso):
    d=dt.datetime.fromisoformat(d_iso)
    return f"{MONTHS_RU[d.month]} {d.year}"

# ---- main block ----------------------------------------------------------
def get_macro_block():
    lines=[]
    for cfg in SERIES.values():
        flag=cfg["flag"]

        # CPI
        try:
            if cfg["cpi_yoy"]:
                cpi,d,age=_fred_latest(cfg["cpi_yoy"])
            else:
                cpi,d=_yoy_from_index(cfg["cpi_idx"]); age=(dt.datetime.today()-dt.datetime.fromisoformat(d)).days
        except Exception as e_fred:
            try:
                cpi,d,age=_wb_latest(cfg["iso"],cfg["wb_cpi"])
                log(f"ℹ️ CPI {flag} via WB {cpi:.2f} ({d})")
            except Exception as e_wb:
                log(f"❌ CPI {flag} FRED:{e_fred} WB:{e_wb}")
                continue

        stale=" 🕒" if age>STALE_BADGE_DAYS else ""

        # PPI
        ppi_s="PPI n/a"
        if cfg["ppi"]:
            try:
                ppi,_=_yoy_from_index(cfg["ppi"])
                ppi_s=f"PPI {ppi:.1f} %"
            except Exception as e: log(f"⚠️ PPI {flag} {e}")

        # Rate
        rate_s="Rate n/a"
        if cfg["rate"]:
            try:
                rate,_,_=_fred_latest(cfg["rate"])
                rate_s=f"Rate {rate:.2f} %"
            except Exception as e: log(f"⚠️ RATE {flag} {e}")

        # Unemployment
        unemp_s=""
        if cfg["unemp"]:
            try:
                un,_,_=_fred_latest(cfg["unemp"])
                unemp_s=f" | Unemp {un:.1f} %"
            except Exception as e: log(f"⚠️ UNEMP {flag} {e}")

        lines.append(
            f"{flag} CPI {cpi:.1f} %{stale} | {ppi_s} | {rate_s}{unemp_s}  ({_rus(d)})"
        )

    if not lines: return ""
    header=("📊 Макроэкономика\n"
            "<b>Легенда:</b> CPI — годовая инфляция, PPI — цены производителей, "
            "Rate — ставка ЦБ, Unemp — безработица\n\n")
    return header+"\n".join(lines)
