"""Fetching: live bond quotes and yield history (CNBC), credit spreads and inflation-linked yields (FRED),
public finances (IMF), central-bank rates (BIS), currencies and bond volatility (Yahoo) and credit ratings
(Wikipedia's table of the three agencies' ratings).

Slow-moving data is cached in data/cache/ so the site can refresh every ~15 minutes without
re-downloading years of history; if a source is down, the last good copy is used instead.
"""
import csv
import html
import io
import json
import re
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache"
# FRED and the IMF turn away browser-like and default Python user agents; an honest name works.
UA = {"User-Agent": "BondCompass/1.0 (+https://github.com/maxgilbertson/bond-compass)"}
HISTORY_FROM = "2016-01-01"
_locks = {}


def get(url, timeout=30, tries=3, headers=None):
    err = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers=headers or UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001 - network hiccups are retried, then reported
            err = e
            time.sleep(0.8 * (attempt + 1))
    raise RuntimeError(f"{url[:80]}: {err}")


def cached(name, max_age, fn, complete=None, retry=6 * 3600):
    """fn(old)'s result, reused for max_age seconds; the last good copy if fn fails. Returns (data, saved_at).

    complete(data) -> False marks a saved copy with gaps: it gets another try after `retry` seconds.
    """
    path = CACHE / f"{name}.json"
    lock = _locks.setdefault(name, threading.Lock())
    with lock:
        old, seeded = None, False
        # the saved copy, or failing that the starter copy kept in the repository (data/seed/)
        for f in (path, ROOT / "data" / "seed" / f"{name}.json"):
            if old is None and f.exists():
                try:
                    old, seeded = json.loads(f.read_text(encoding="utf-8")), f != path
                except ValueError:
                    old = None
        age = time.time() - old["at"] if old else None
        if old and age < max_age and (complete is None or complete(old["data"]) or (age < retry and not seeded)):
            return old["data"], old["at"]
        try:
            data = fn(old["data"] if old else None)
            if not data:
                raise RuntimeError("empty result")
        except Exception as e:  # noqa: BLE001
            print(f"[{name}] refresh failed ({e}); using the saved copy", flush=True)
            if old:
                return old["data"], old["at"]
            raise
        CACHE.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"at": time.time(), "data": data}, separators=(",", ":")), encoding="utf-8")
        tmp.replace(path)
        return data, time.time()


def _day(iso):
    """'2026-10-05' -> Unix time of that day's midnight (UTC)."""
    return int(datetime.strptime(iso[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())


# ---------------------------------------------------------------- CNBC: live quotes and history

def _num(s):
    if s in (None, "", "UNCH"):
        return 0.0 if s == "UNCH" else None
    try:
        return float(str(s).replace("%", "").replace(",", "").replace("+", ""))
    except ValueError:
        return None


def quotes(symbols):
    """Latest quote for each symbol: yield, change, coupon, maturity, price and when it last traded."""
    out = {}

    def batch(syms):
        url = ("https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol?symbols="
               + urllib.parse.quote("|".join(syms), safe="|=") +
               "&requestMethod=itv&noform=1&partnerId=2&fund=1&exthrs=1&output=json&events=1")
        q = json.loads(get(url, timeout=25))["FormattedQuoteResult"]["FormattedQuote"]
        return q if isinstance(q, list) else [q]

    chunks = [symbols[i:i + 40] for i in range(0, len(symbols), 40)]
    with ThreadPoolExecutor(max_workers=4) as ex:
        for res in ex.map(lambda c: _safe(batch, c), chunks):
            for x in res or []:
                y = _num(x.get("last"))
                if x.get("code") not in (0, "0") or y is None or "%" not in str(x.get("last")):
                    continue
                lt = x.get("last_time")
                try:
                    when = datetime.strptime(lt, "%Y-%m-%dT%H:%M:%S.%f%z").timestamp() if lt else None
                except ValueError:
                    when = None
                out[x["symbol"]] = {
                    "y": y, "chg": _num(x.get("change")), "prev": _num(x.get("previous_day_closing")),
                    "coupon": _num(x.get("coupon")), "mat": x.get("maturity_date"),
                    "price": _num(x.get("bond_last_price")), "pchg": _num(x.get("bond_change_price")),
                    "hi1y": _num(x.get("yrhiprice")), "lo1y": _num(x.get("yrloprice")),
                    "time": when, "name": x.get("name"), "open": x.get("curmktstatus") == "REG_MKT",
                }
    return out


def _safe(fn, *a):
    try:
        return fn(*a)
    except Exception as e:  # noqa: BLE001
        print(f"[{fn.__name__} {a[0] if a and isinstance(a[0], str) else ''}] {e}", flush=True)
        return None


def _bars(sym):
    end = date.today().strftime("%Y%m%d") + "000000"
    url = (f"https://ts-api.cnbc.com/harmony/app/bars/{urllib.parse.quote(sym)}/1D/"
           f"{HISTORY_FROM.replace('-', '')}000000/{end}/adjusted/EST5EDT.json")
    bars = (json.loads(get(url, timeout=30)).get("barData") or {}).get("priceBars") or []
    out = []
    for b in bars:
        v = _num(b.get("close"))
        if v is not None:
            t = b["tradeTime"]
            out.append([_day(f"{t[:4]}-{t[4:6]}-{t[6:8]}"), round(v, 4)])
    return out


def history(symbols):
    """Daily closing yields since 2016 for each symbol, refreshed once a day."""
    def fetch(old):
        res = dict(old or {})
        with ThreadPoolExecutor(max_workers=8) as ex:
            for sym, bars in zip(symbols, ex.map(lambda s: _safe(_bars, s), symbols)):
                if bars:
                    res[sym] = bars
        return res if len(res) >= len(symbols) * 0.6 else None
    data, at = cached("history", 20 * 3600, fetch)
    missing = [s for s in symbols if s not in data]
    if missing and time.time() - at > 3600:  # a market added since the last full download
        extra = {s: b for s, b in zip(missing, map(lambda s: _safe(_bars, s), missing)) if b}
        if extra:
            data.update(extra)
            (CACHE / "history.json").write_text(json.dumps({"at": at, "data": data}, separators=(",", ":")),
                                                 encoding="utf-8")
    return data


# ---------------------------------------------------------------- FRED: credit spreads, TIPS, breakevens

def fred(ids):
    def one(sid):
        cosd = (date.today() - timedelta(days=3700)).isoformat()
        text = get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd={cosd}", timeout=30).decode()
        rows = list(csv.reader(io.StringIO(text)))[1:]
        return [[_day(d), float(v)] for d, v in rows if v not in ("", ".")]

    def fetch(old):
        res = dict(old or {})
        with ThreadPoolExecutor(max_workers=6) as ex:
            for sid, s in zip(ids, ex.map(lambda i: _safe(one, i), ids)):
                if s:
                    res[sid] = s
        return res if res else None
    return cached("fred", 4 * 3600, fetch)


# ---------------------------------------------------------------- IMF World Economic Outlook

def imf(indicators, countries):
    has_countries = lambda d: sum(c in (d.get("GGXWDG_NGDP") or {}) for c in countries) >= len(countries) - 1

    def one(ind):
        d = json.loads(get(f"https://www.imf.org/external/datamapper/api/v1/{ind}", timeout=60, tries=2))
        vals = d["values"][ind]
        return {c: {int(y): v for y, v in vals.get(c, {}).items() if v is not None} for c in countries if c in vals}

    def fetch(old):
        res = dict(old or {})
        stale = not old or old.get("_full", 0) < time.time() - 7 * 86400 or not has_countries(old)
        todo = indicators if stale else [i for i in indicators if i not in old]
        if todo == indicators:
            res["_full"] = time.time()
        with ThreadPoolExecutor(max_workers=2) as ex:  # the IMF's firewall turns away bursts of requests
            for ind, v in zip(todo, ex.map(lambda i: _safe(one, i), todo)):
                if v:
                    res[ind] = v
        return res if sum(i in res for i in indicators) >= len(indicators) // 2 else None
    data, at = cached("imf", 7 * 86400, fetch, complete=lambda d: all(i in d for i in indicators) and has_countries(d))
    # JSON keys are strings; turn the years back into numbers
    return {ind: {c: {int(y): v for y, v in s.items()} for c, s in per.items()} for ind, per in data.items() if ind != "_full"}, at


# ---------------------------------------------------------------- BIS central-bank policy rates

def policy_rates(codes):
    def fetch(old):
        start = (date.today() - timedelta(days=800)).isoformat()
        url = f"https://stats.bis.org/api/v1/data/WS_CBPOL/D.{'+'.join(codes)}/all?startPeriod={start}&format=csv"
        rows = csv.DictReader(io.StringIO(get(url, timeout=60).decode("utf-8")))
        res = {}
        for r in rows:
            v = r.get("OBS_VALUE")
            if v and v.lower() != "nan":
                res.setdefault(r["REF_AREA"], []).append([_day(r["TIME_PERIOD"]), float(v)])
        for s in res.values():
            s.sort()
        return res or None
    return cached("bis", 12 * 3600, fetch, complete=lambda d: all(c in d for c in codes), retry=3600)


def boe(codes):
    """Bank of England daily yield-curve series since 2016 (about two business days behind), every 6 hours."""
    def fetch(old):
        url = ("https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp?csv.x=yes&Datefrom=01/Jan/2016"
               f"&Dateto=now&SeriesCodes={','.join(codes)}&CSVF=TN&UsingCodes=Y&VPD=Y&VFD=N")
        text = get(url, timeout=60).decode("utf-8-sig")
        if not text.startswith("DATE"):
            raise RuntimeError("unexpected reply from the Bank of England database")
        res = {}
        for r in csv.DictReader(io.StringIO(text)):
            t = int(datetime.strptime(r["DATE"], "%d %b %Y").replace(tzinfo=timezone.utc).timestamp())
            for c in codes:
                if r.get(c):
                    res.setdefault(c, []).append([t, float(r[c])])
        return res or None
    return cached("boe", 6 * 3600, fetch, complete=lambda d: all(c in d for c in codes), retry=3600)


def policy_rates_monthly(codes):
    """Month-end policy rates since 2015 (for the test on past data), refreshed weekly."""
    def fetch(old):
        url = f"https://stats.bis.org/api/v1/data/WS_CBPOL/M.{'+'.join(codes)}/all?startPeriod=2015-01&format=csv"
        res = {}
        for r in csv.DictReader(io.StringIO(get(url, timeout=60).decode("utf-8"))):
            v = r.get("OBS_VALUE")
            if v and v.lower() != "nan":
                y, m = map(int, r["TIME_PERIOD"].split("-"))
                end = datetime(y + (m == 12), m % 12 + 1, 1, tzinfo=timezone.utc).timestamp() - 1
                res.setdefault(r["REF_AREA"], []).append([int(end), float(v)])
        for s in res.values():
            s.sort()
        return res or None
    return cached("bis_monthly", 7 * 86400, fetch, complete=lambda d: all(c in d for c in codes))


# ---------------------------------------------------------------- Yahoo: currencies and the MOVE index

def yahoo(symbol, rng="2y"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?range={rng}&interval=1d"
    res = json.loads(get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BondCompass/1.0"},
                         timeout=25))["chart"]["result"][0]
    closes = res["indicators"]["quote"][0]["close"]
    pts = [[t, c] for t, c in zip(res.get("timestamp") or [], closes) if c is not None]
    meta = res["meta"]
    if meta.get("regularMarketPrice") and pts and meta.get("regularMarketTime", 0) > pts[-1][0]:
        pts.append([meta["regularMarketTime"], meta["regularMarketPrice"]])
    return {"t": [p[0] for p in pts], "c": [p[1] for p in pts], "time": meta.get("regularMarketTime")}


def fund_prices(funds):
    """Price, currency and total returns (distributions reinvested) of the London-listed bond funds, hourly."""
    def one(f):
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(f['yahoo'])}"
               "?range=1y&interval=1d&includeAdjustedClose=true")
        res = json.loads(get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BondCompass/1.0"},
                             timeout=25))["chart"]["result"][0]
        q, meta = res["indicators"], res["meta"]
        adj = (q.get("adjclose") or [{}])[0].get("adjclose") or q["quote"][0]["close"]
        pts = [[t, a] for t, a in zip(res.get("timestamp") or [], adj) if a]
        if len(pts) < 20:
            return None
        # a bond fund never moves 40% in a day: a jump like that is a share split or consolidation that the
        # price history hasn't been adjusted for, so rescale everything before it
        for k in range(len(pts) - 1, 0, -1):
            ratio = pts[k][1] / pts[k - 1][1]
            if ratio < 0.6 or ratio > 1.6:
                for j in range(k):
                    pts[j][1] *= ratio
        pence = meta.get("currency") == "GBp"
        price = meta.get("regularMarketPrice") or q["quote"][0]["close"][-1]
        now = pts[-1][0]
        back = lambda days: next((a for t, a in reversed(pts) if t <= now - days * 86400), None)
        r = lambda days: (pts[-1][1] / back(days) - 1) if back(days) else None
        return {"yahoo": f["yahoo"], "price": price / 100 if pence else price, "ccy": "GBP" if pence else meta.get("currency"),
                "r1m": r(30), "r3m": r(91), "r1y": (pts[-1][1] / pts[0][1] - 1) if pts[0][0] <= now - 350 * 86400 else None,
                "time": meta.get("regularMarketTime"), "spark": [round(a, 4) for _, a in pts[::5]]}

    def fetch(old):
        with ThreadPoolExecutor(max_workers=8) as ex:
            got = {f["yahoo"]: d for f, d in zip(funds, ex.map(lambda f: _safe(one, f), funds)) if d}
        return got if len(got) >= len(funds) // 2 else None
    return cached("funds", 3600, fetch)


def yahoo_all(symbols):
    with ThreadPoolExecutor(max_workers=8) as ex:
        return {s: d for s, d in zip(symbols, ex.map(lambda s: _safe(yahoo, s), symbols)) if d and d["c"]}


# ---------------------------------------------------------------- credit ratings (S&P, Moody's, Fitch)

RATINGS_FILE = ROOT / "data" / "ratings.json"


def ratings(names):
    """Each country's three agency ratings, outlooks and dates, from Wikipedia's maintained table (weekly)."""
    def fetch(old):
        url = ("https://en.wikipedia.org/w/api.php?action=parse&page=List_of_countries_by_credit_rating"
               "&prop=text&format=json&formatversion=2")
        page = json.loads(get(url, timeout=40))["parse"]["text"]
        tables = re.findall(r"<table.*?</table>", page, re.S)
        clean = lambda c: re.sub(r"\s+", " ", html.unescape(re.sub(r"<.*?>", " ", re.sub(r"<sup.*?</sup>", "", c, flags=re.S)))).strip()
        res = {}
        for tb, agency in zip(tables[:3], ("sp", "fitch", "moodys")):
            for row in re.findall(r"<tr.*?</tr>", tb, re.S)[1:]:
                cells = [clean(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]
                if len(cells) >= 4 and cells[0] in names:
                    res.setdefault(cells[0], {})[agency] = {"r": cells[1].replace("−", "-"), "o": cells[2], "d": cells[3]}
        if len(res) < len(names) * 0.8:
            return None
        RATINGS_FILE.write_text(json.dumps({"checked": date.today().isoformat(), "ratings": res}, indent=1,
                                           ensure_ascii=False), encoding="utf-8")
        return {"checked": date.today().isoformat(), "ratings": res}
    try:
        data, _ = cached("ratings", 7 * 86400, fetch, complete=lambda d: all(n in d.get("ratings", {}) for n in names), retry=3600)
        return data
    except Exception:  # noqa: BLE001 - fall back to the copy kept in the repository
        return json.loads(RATINGS_FILE.read_text(encoding="utf-8"))
