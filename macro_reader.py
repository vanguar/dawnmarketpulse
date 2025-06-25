# macro_reader.py
import os, requests, datetime as dt

FRED_KEY = os.getenv("FRED_KEY")
BASE = "https://api.stlouisfed.org/fred/series/observations"

MONTHS_RU = {
    1:"янв",2:"фев",3:"мар",4:"апр",5:"май",6:"июн",
    7:"июл",8:"авг",9:"сен",10:"окт",11:"ноя",12:"дек"
}

SERIES = {
    "US": {"flag":"🇺🇸", "cpi":"CPALTT01USM657N",  "unemp":"UNRATE"},
    "EU": {"flag":"🇪🇺", "cpi":"CPALTT01EZM657N",  "unemp":"LRHUTTTTEZM156S"},
    "JP": {"flag":"🇯🇵", "cpi":"CPALTT01JPM657N",  "unemp":None},
}

MAX_AGE_DAYS = 400

def _latest(sid:str):
    url=(f"{BASE}?series_id={sid}&api_key={FRED_KEY}"
         "&file_type=json&sort_order=desc&limit=1")
    obs=requests.get(url,timeout=10).json()["observations"][0]
    date_iso=obs["date"]
    if (dt.datetime.today()-dt.datetime.fromisoformat(date_iso)
        ).days>MAX_AGE_DAYS:
        raise ValueError("data too old")
    return float(obs["value"]),date_iso

def _rus_date(iso:str)->str:
    d=dt.datetime.fromisoformat(iso)
    return f"{MONTHS_RU[d.month]} {d.year}"

def get_macro_block()->str:
    lines=[]
    for data in SERIES.values():
        flag=data["flag"]
        try:
            cpi,val_date=_latest(data["cpi"])
        except Exception:
            continue  # без CPI страну не показываем
        cpi_part=f"CPI {cpi:.1f} %"

        unemp_part=""
        if data["unemp"]:
            try:
                unemp,_=_latest(data["unemp"])
                unemp_part=f" | Unemp {unemp:.1f} %"
            except Exception:
                pass

        lines.append(f"{flag} {cpi_part}{unemp_part}  ({_rus_date(val_date)})")

    return (
        "📊 Макроэкономика (CPI — инфляция г/г, Unemp — безработица)\n"
        + "\n".join(lines)
    ) if lines else ""
