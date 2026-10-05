"""Official sources for markets CNBC doesn't quote: Norway, Singapore, Peru, Poland, Malaysia and the Philippines.

Each fetcher returns {symbol: [[t, yield], ...]} (daily closes, oldest first) for symbols like "NO10Y@X", plus
optional extra detail (maturity, coupon) for the latest bond in each maturity bucket. build() turns the latest
point into a quote, so these markets get the same analytics as the rest. Everything is cached once a day.

  Norway       Norges Bank open data (SDMX), daily generic government yields, history from 2019
  Singapore    Monetary Authority of Singapore, daily benchmark SGS yields (form download), history from 1998
  Peru         Banco Central de Reserva del Perú statistics API, daily 10-year sol bond, history from 2005
  Poland       BondSpot fixing (the official Treasury bond fixing), one page per day: the bond nearest each maturity
  Malaysia     Bank Negara Malaysia, daily MGS benchmark closing yields, one page per day
  Philippines  Asian Development Bank AsianBondsOnline (source: Bloomberg), latest curve plus a few past points
"""
import csv
import html
import io
import json
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

import sources

DAY = 86400
TENOR_Y = {"1M": 1 / 12, "3M": 0.25, "6M": 0.5, "1Y": 1, "2Y": 2, "3Y": 3, "4Y": 4, "5Y": 5, "7Y": 7, "10Y": 10,
           "15Y": 15, "20Y": 20, "25Y": 25, "30Y": 30, "50Y": 50}


def sym(code, tenor):
    return f"{code}{tenor}@X"


def _ts(d, hour=16):
    return int(datetime(d.year, d.month, d.day, hour, tzinfo=timezone.utc).timestamp())


def _get(url, data=None, headers=None, timeout=60):
    if data is None:
        return sources.get(url, timeout=timeout, headers=headers)
    req = sources.urllib.request.Request(url, data=data, headers=headers or sources.UA)
    with sources.urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _merge(old, new):
    """Combine two {symbol: [[t, y]]} dicts, newer values winning on the same day."""
    out = {}
    for s in set(old or {}) | set(new or {}):
        days = {p[0] // DAY: p for p in (old or {}).get(s, [])}
        days.update({p[0] // DAY: p for p in (new or {}).get(s, [])})
        out[s] = [days[k] for k in sorted(days)]
    return out

# ---------------------------------------------------------------- Norway

def norway(old):
    start = "2016-01-01" if not old else (date.today() - timedelta(days=20)).isoformat()
    text = _get(f"https://data.norges-bank.no/api/data/GOVT_GENERIC_RATES/B..GBON+TBIL.?format=csv&locale=en&startPeriod={start}").decode("utf-8-sig")
    rows = csv.DictReader(io.StringIO(text), delimiter=";")
    tenor = {"3M": "3M", "6M": "6M", "12M": "1Y", "3Y": "3Y", "5Y": "5Y", "7Y": "7Y", "10Y": "10Y"}
    res = {}
    for r in rows:
        t = tenor.get(r["TENOR"])
        if t and r["OBS_VALUE"]:
            res.setdefault(sym("NO", t), []).append([_ts(date.fromisoformat(r["TIME_PERIOD"]), 14), float(r["OBS_VALUE"])])
    return _merge(old, res)

# ---------------------------------------------------------------- Singapore

def singapore(old):
    url = "https://eservices.mas.gov.sg/statistics/fdanet/BenchmarkPricesAndYields.aspx"
    page = _get(url).decode("utf-8", "replace")
    form = dict(re.findall(r'<input type="hidden" name="([^"]+)" id="[^"]*" value="([^"]*)"', page))
    p = "ctl00$ContentPlaceHolder1$"
    start = date(2016, 1, 1) if not old else date.today() - timedelta(days=40)
    today = date.today()
    form.update({p + "StartYearDropDownList": str(start.year), p + "StartMonthDropDownList": str(start.month),
                 p + "EndYearDropDownList": str(today.year), p + "EndMonthDropDownList": str(today.month),
                 p + "FrequencyDropDownList": "D", p + "DownloadButton": "Download"})
    names = {"SixMonthTreasuryBill": "6M", "OneYearTreasuryBill": "1Y", "TwoYearBond": "2Y", "FiveYearBond": "5Y",
             "SevenYearBond": "7Y", "TenYearBond": "10Y", "FifteenYearBond": "15Y", "TwentyYearBond": "20Y",
             "ThirtyYearBond": "30Y", "FiftyYearBond": "50Y"}
    for n in names:
        form[p + n + "YieldCheckBox"] = "on"
    text = _get(url, urllib.parse.urlencode(form).encode(),
                dict(sources.UA, **{"Content-Type": "application/x-www-form-urlencoded"}), timeout=120).decode("utf-8", "replace")
    lines = list(csv.reader(io.StringIO(text)))
    head = next(l for l in lines if len(l) > 4 and "Yield" in "".join(l))
    cols = []
    for h in head[3:]:
        m = re.search(r"(\d+)-(Month|Year)", h)
        cols.append(None if not m else f"{m.group(1)}{'M' if m.group(2) == 'Month' else 'Y'}")
    res, y, mo = {}, None, None
    months = {m: i + 1 for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}
    for l in lines[lines.index(head) + 1:]:
        if len(l) < 4 or not l[2].strip().isdigit():
            continue
        y = int(l[0]) if l[0].strip() else y
        mo = months.get(l[1].strip(), mo) if l[1].strip() else mo
        t = _ts(date(y, mo, int(l[2])), 10)
        for c, v in zip(cols, l[3:]):
            if c and v.strip():
                res.setdefault(sym("SG", "1Y" if c == "1Y" else c), []).append([t, float(v)])
    return _merge(old, res)

# ---------------------------------------------------------------- Peru

SPANISH = {"Ene": 1, "Feb": 2, "Mar": 3, "Abr": 4, "May": 5, "Jun": 6, "Jul": 7, "Ago": 8, "Set": 9, "Sep": 9, "Oct": 10, "Nov": 11, "Dic": 12}


def peru(old):
    start = "2016-01-01" if not old else (date.today() - timedelta(days=30)).isoformat()
    d = json.loads(_get(f"https://estadisticas.bcrp.gob.pe/estadisticas/series/api/PD31893DD/json/{start}/{date.today().isoformat()}"))
    res = []
    for p in d.get("periods", []):
        v = p["values"][0]
        if v in ("n.d.", "", None):
            continue
        dd, mm, yy = p["name"].split(".")
        res.append([_ts(date(2000 + int(yy), SPANISH[mm], int(dd)), 20), float(v)])
    return _merge(old, {sym("PE", "10Y"): res})

# ---------------------------------------------------------------- Poland (one page per day)

def _poland_day(d):
    page = _get(f"https://www.bondspot.pl/fixing_obligacji?date={d.strftime('%Y%m%d')}", timeout=30).decode("utf-8", "replace")
    out = []
    for row in re.findall(r"<tr.*?</tr>", page, re.S):
        c = [html.unescape(re.sub(r"<.*?>", "", x)).strip() for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]
        if len(c) >= 9 and re.fullmatch(r"(OK|PS|DS|WS)\d{4}", c[1]) and c[8] not in ("-", ""):
            mm, yy = int(c[1][2:4]), 2000 + int(c[1][4:6])
            mat = date(yy, mm, 25)
            out.append({"name": c[1], "mat": mat, "y": float(c[8].replace(",", ".")), "price": float(c[7].replace(",", "."))})
    return out


def _bucket(bonds, d, buckets=("1Y", "2Y", "3Y", "5Y", "7Y", "10Y")):
    """The bond nearest each maturity bucket on day d (within 35% of the bucket)."""
    out = {}
    for t in buckets:
        want = TENOR_Y[t]
        cands = [(abs((b["mat"] - d).days / 365.25 - want), b) for b in bonds if (b["mat"] - d).days > 120]
        if cands:
            gap, b = min(cands, key=lambda x: x[0])
            if gap <= want * 0.35:
                out[t] = b
    return out


def poland(old):
    today = date.today()
    have = {p[0] // DAY for p in (old or {}).get(sym("PL", "10Y"), [])}
    days = [today - timedelta(days=k) for k in range(0, 15)]
    if not old:  # first run: a point a week (Wednesdays) for three years, so the history means something from day one
        wed = today - timedelta(days=(today.weekday() - 2) % 7 + 14)
        days += [wed - timedelta(days=k) for k in range(0, 3 * 365, 7)]
    days = [d for d in days if d.weekday() < 5 and _ts(d, 0) // DAY not in have]
    res, detail = {}, {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        for d, bonds in zip(days, ex.map(lambda d: sources._safe(_poland_day, d), days)):
            for t, b in _bucket(bonds or [], d).items():
                res.setdefault(sym("PL", t), []).append([_ts(d, 15), b["y"]])
                if d == max(x for x in days if x <= today):
                    detail[sym("PL", t)] = {"mat": b["mat"].isoformat(), "name": b["name"]}
    for s in res:
        res[s].sort()
    out = _merge(old, res)
    out["_detail"] = {**(old or {}).get("_detail", {}), **detail}
    return out

# ---------------------------------------------------------------- Malaysia (one page per day)

def _malaysia_day(d):
    page = _get("https://www.bnm.gov.my/government-securities-yield?p_p_id=my_gov_bnm_yield_display_portlet&p_p_lifecycle=0"
                f"&p_p_state=normal&p_p_mode=view&_my_gov_bnm_yield_display_portlet_tradingDateTxt={d.isoformat()}", timeout=60).decode("utf-8", "replace")
    page = page[:page.find("Government Investment Issues")] if "Government Investment Issues" in page else page
    out = {}
    for row in re.findall(r"<tr.*?</tr>", page, re.S):
        c = [html.unescape(re.sub(r"<.*?>", "", x)).strip() for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]
        m = re.fullmatch(r"(\d+)-year", c[0]) if c else None
        if m and len(c) >= 6:
            try:
                mat = datetime.strptime(c[1], "%b-%Y").date().replace(day=15)
                out[f"{m.group(1)}Y"] = {"y": float(c[5]), "coupon": float(c[2]), "mat": mat.isoformat()}
            except ValueError:
                continue
    return out


def malaysia(old):
    today = date.today()
    have = {p[0] // DAY for p in (old or {}).get(sym("MY", "10Y"), [])}
    days = [today - timedelta(days=k) for k in range(0, 10)]
    if not old:  # first run: a point a week (Wednesdays) for a year; each page is large, so not further
        wed = today - timedelta(days=(today.weekday() - 2) % 7 + 14)
        days += [wed - timedelta(days=k) for k in range(0, 365, 7)]
    days = [d for d in days if d.weekday() < 5 and _ts(d, 0) // DAY not in have]
    res, detail, latest = {}, {}, None
    with ThreadPoolExecutor(max_workers=4) as ex:
        for d, got in zip(days, ex.map(lambda d: sources._safe(_malaysia_day, d), days)):
            for t, b in (got or {}).items():
                res.setdefault(sym("MY", t), []).append([_ts(d, 9), b["y"]])
                if got and (latest is None or d > latest[0]):
                    latest = (d, got)
    if latest:
        detail = {sym("MY", t): {"mat": b["mat"], "coupon": b["coupon"]} for t, b in latest[1].items()}
    for s in res:
        res[s].sort()
    out = _merge(old, res)
    out["_detail"] = {**(old or {}).get("_detail", {}), **detail}
    return out

# ---------------------------------------------------------------- Philippines (latest curve)

def philippines(old):
    page = _get("https://asianbondsonline.adb.org/charts/government_bond_yields.php?economies=PH",
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BondCompass/1.0"}).decode("utf-8", "replace")
    res = {}
    for name, data in re.findall(r"name:\s*'([^']+)',\s*marker:[^}]*},\s*data:\s*(\[\[.*?\]\])", page, re.S):
        try:
            d = datetime.strptime(name, "%d-%b-%y").date()
        except ValueError:
            continue  # "Previous Week" etc. have no exact date; our own daily record covers those
        for x, y in json.loads(data):
            t = next((k for k, v in TENOR_Y.items() if abs(v - x) < 0.05), None)
            if t:
                res.setdefault(sym("PH", t), []).append([_ts(d, 9), float(y)])
    return _merge(old, res)


FETCHERS = {"NO": norway, "SG": singapore, "PE": peru, "PL": poland, "MY": malaysia, "PH": philippines}


def fetch_all():
    """{symbol: history} for every extra market, plus "_detail" (maturity/coupon of the latest bonds)."""
    def one(code):
        data, _ = sources.cached(f"extra_{code}", 20 * 3600, FETCHERS[code])
        return data
    out, detail = {}, {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        for code, data in zip(FETCHERS, ex.map(lambda c: sources._safe(one, c), FETCHERS)):
            if data:
                detail.update(data.pop("_detail", {}) if isinstance(data.get("_detail"), dict) else {})
                out.update({k: v for k, v in data.items() if not k.startswith("_")})
    return out, detail
