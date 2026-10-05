"""Markets with only monthly government bond yields from free official sources: shown on the Countries tab
in their own table, never mixed into the live tables or the score (a month-old yield isn't comparable).

  Israel      Bank of Israel SDMX: nominal zero-coupon 2/5/10-year yields, monthly averages
  Colombia    Banco de la República SDMX: TES 1/5/10-year yields (published as fractions)
  Czech Rep.  ECB harmonised long-term rate (10-year), monthly
  Denmark     ECB harmonised long-term rate (10-year), monthly
  Romania     ECB harmonised long-term rate (10-year), monthly
  Taiwan      Central Bank of the Republic of China (Taiwan): 10-year secondary-market yield, monthly
"""
import csv
import io
import json
import re
from datetime import datetime, timezone

import sources

# code, name, region, currency, IMF code, rating name, source label
MONTHLY = [
    ("IL", "Israel", "Middle East & Africa", "ILS", "ISR", "Israel", "Bank of Israel"),
    ("CO", "Colombia", "Americas", "COP", "COL", "Colombia", "Banco de la República"),
    ("CZ", "Czech Republic", "Europe", "CZK", "CZE", "Czech Republic", "ECB (harmonised long-term rate)"),
    ("DK", "Denmark", "Europe", "DKK", "DNK", "Denmark", "ECB (harmonised long-term rate)"),
    ("RO", "Romania", "Europe", "RON", "ROU", "Romania", "ECB (harmonised long-term rate)"),
    ("TW", "Taiwan", "Asia-Pacific", "TWD", "TWN", "Taiwan", "Central Bank of the Republic of China (Taiwan)"),
]


def _month_ts(y, m):
    return int(datetime(y, m, 15, tzinfo=timezone.utc).timestamp())


def _ecb(code, ccy):
    url = f"https://data-api.ecb.europa.eu/service/data/IRS/M.{code}.L.L40.CI.0000.{ccy}.N.Z?format=csvdata&startPeriod=2016-01"
    rows = csv.DictReader(io.StringIO(sources.get(url, timeout=40).decode("utf-8")))
    out = []
    for r in rows:
        if r.get("OBS_VALUE"):
            y, m = map(int, r["TIME_PERIOD"].split("-"))
            out.append([_month_ts(y, m), float(r["OBS_VALUE"])])
    return {"10Y": sorted(out)}


def _israel():
    out = {}
    for t in ("02Y", "05Y", "10Y"):
        url = f"https://edge.boi.gov.il/FusionEdgeServer/sdmx/v2/data/dataflow/BOI.STATISTICS/ZCM/1.0/ZC_TSB_ZND_{t}_MA?format=csv"
        rows = list(csv.reader(io.StringIO(sources.get(url, timeout=40).decode("utf-8-sig"))))
        head = rows[0]
        ti, vi = head.index("TIME_PERIOD"), head.index("OBS_VALUE")
        pts = []
        for r in rows[1:]:
            if len(r) > vi and r[vi]:
                y, m = map(int, r[ti][:7].split("-"))
                if y >= 2016:
                    pts.append([_month_ts(y, m), float(r[vi])])
        out[t.lstrip("0")] = sorted(pts)
    return out


def _colombia():
    xml = sources.get("https://totoro.banrep.gov.co/nsi-jax-ws/rest/data/ESTAT,DF_TES_MONTHLY_HIST,1.0/all/ALL/", timeout=60,
                      headers=dict(sources.UA, Accept="application/xml")).decode("utf-8")  # it answers 500 without an Accept header
    out = {}
    for series in re.findall(r"<generic:Series>(.*?)</generic:Series>", xml, re.S):
        code = re.search(r'value="(IRGBRY\d\d)"', series)
        if not code:
            continue
        t = {"IRGBRY01": "1Y", "IRGBRY05": "5Y", "IRGBRY10": "10Y"}.get(code.group(1))
        if not t:
            continue
        pts = []
        for per, val in re.findall(r'<generic:ObsDimension value="(\d{4}-\d{2})[^"]*"\s*/>\s*<generic:ObsValue value="([^"]+)"', series):
            y, m = map(int, per.split("-"))
            if y >= 2016:
                v = float(val)
                pts.append([_month_ts(y, m), v * 100 if v < 1 else v])
        out[t] = sorted(pts)
    return out


def _taiwan():
    d = json.loads(sources.get("https://cpx.cbc.gov.tw/api/DataAPI/Get?FileName=EG43M01", timeout=40))
    rows = d.get("data", {}).get("dataSets") or d.get("dataSets") or d.get("data") or []
    pts = []
    for r in rows:
        r = list(r.values()) if isinstance(r, dict) else r
        m = re.match(r"(\d{4})M(\d{2})", str(r[0]))
        if m and r[-1] not in (None, "", "-"):
            try:
                y, mo = int(m.group(1)), int(m.group(2))
                if y >= 2016:
                    pts.append([_month_ts(y, mo), float(r[-1])])
            except ValueError:
                continue
    return {"10Y": sorted(pts)}


FETCH = {"IL": _israel, "CO": _colombia, "CZ": lambda: _ecb("CZ", "CZK"), "DK": lambda: _ecb("DK", "DKK"),
         "RO": lambda: _ecb("RO", "RON"), "TW": _taiwan}


def fetch_all():
    """{code: {tenor: [[t, y]]}}, refreshed daily (the data itself changes monthly)."""
    def fetch(old):
        res = dict(old or {})
        for code, fn in FETCH.items():
            got = sources._safe(lambda f=fn: f())
            if got and any(got.values()):
                res[code] = got
        return res or None
    data, _ = sources.cached("monthly", 24 * 3600, fetch, complete=lambda d: all(c in d for c in FETCH), retry=6 * 3600)
    return data
