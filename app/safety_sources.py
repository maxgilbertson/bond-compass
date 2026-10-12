"""Slow-moving data for judging how safe each government is: how its debt is structured (when it falls due, what
rate it pays, which currency it is in, who holds it), its institutions, reserves and default record.

Each source is cached for a week or more (sources.cached keeps the last good copy if a refresh fails, and
data/seed/ holds a starter copy), and data/*.json keeps the figures that only change once or twice a year.

  ECB Data Portal, GFS     EU governments' debt securities, monthly: average remaining maturity, share due
                           within 12 months, share at floating or inflation-linked rates
  BIS debt securities      43 markets, quarterly (WS_NA_SEC_DSS) plus international bonds (WS_DEBT_SEC2_PUB):
                           share due within a year, variable and inflation-linked, foreign currency, held abroad
  IMF Fiscal Monitor       data/fiscal_monitor.json, from the statistical tables (April and October): average
                           term to maturity, gross financing need, share of debt held by non-residents
"""
import csv
import io
import json
import time
from datetime import date

import markets
import monthly_sources
import sources

CODES = [m[0] for m in markets.MARKETS] + [m[0] for m in monthly_sources.MONTHLY]
EU = {"AT", "BE", "DE", "ES", "FI", "FR", "GR", "IE", "IT", "NL", "PT", "CZ", "DK", "HU", "PL", "RO", "SE"}
DAY = 86400


def _rows(raw):
    return csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))


def _num(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if x != x else x  # NaN


def _static(name):
    try:
        return json.loads((sources.ROOT / "data" / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


# ---------------------------------------------------------------- ECB: EU governments' debt securities, monthly

# GFS key: monthly, general government (S13) liabilities (L) and interest (D41); debt securities (F3) and the
# floating or index-linked ones (F3B); maturities all (T), average remaining (TT), up to 3 months and 3 to 12 months
# (TM13 + TM3C), next 12 months (TS); as % of GDP or in years
ECB_KEY = "M.N..W0.S13.S1.N.L+D.LE+D41.F3+F3B.T+TT+TM13+TM3C+TS._Z.XDC_R_B1GQ_CY+YR._T.F+M.V.N+A1._T"


def ecb_profile():
    def fetch(old):
        url = f"https://data-api.ecb.europa.eu/service/data/GFS/{ECB_KEY}?format=csvdata&lastNObservations=1"
        raw = {}
        for r in _rows(sources.get(url, timeout=90)):
            v = _num(r.get("OBS_VALUE"))
            if v is not None and r["REF_AREA"] in EU:
                raw.setdefault(r["REF_AREA"], {})[(r["ACCOUNTING_ENTRY"], r["STO"], r["INSTR_ASSET"], r["MATURITY"],
                                                   r["UNIT_MEASURE"])] = (r["TIME_PERIOD"], v)
        out = {}
        for cc, x in raw.items():
            g = lambda *k: x.get(k, (None, None))[1]
            tot = g("L", "LE", "F3", "T", "XDC_R_B1GQ_CY")
            pct = lambda a: round(100 * a / tot, 1) if a is not None and tot else None
            short = g("L", "LE", "F3", "TM13", "XDC_R_B1GQ_CY")
            out[cc] = {"period": x.get(("L", "LE", "F3", "TT", "YR"), (None,))[0],
                       "atm": round(g("L", "LE", "F3", "TT", "YR"), 1) if g("L", "LE", "F3", "TT", "YR") is not None else None,
                       "securitiesGdp": round(tot, 1) if tot is not None else None,
                       "due1y": pct(None if short is None else short + (g("L", "LE", "F3", "TM3C", "XDC_R_B1GQ_CY") or 0)),
                       "floating": pct(g("L", "LE", "F3B", "T", "XDC_R_B1GQ_CY")),
                       "interest12m": g("D", "D41", "F3", "TS", "XDC_R_B1GQ_CY")}
        return out if len(out) >= 10 else None
    return sources.cached("safety_ecb", 7 * DAY, fetch, retry=DAY)[0]


# ---------------------------------------------------------------- BIS: debt securities statistics, quarterly

BIS = "https://stats.bis.org/api/v1/data"


def bis_profile(codes):
    """Per market: share due within a year, variable and inflation-linked, in foreign currency, held abroad.
    Shares use one valuation (nominal, else market, else face) for top and bottom. Two requests."""
    def fetch(old):
        start = date.today().year - 2
        # FREQ.ADJUSTMENT.REF_AREA.COUNTERPART_AREA(holder: all, non-residents).REF_SECTOR(general, central
        # government).COUNTERPART_SECTOR.CONSOLIDATION.ACCOUNTING_ENTRY.STO.INSTR_ASSET.MATURITY.EXPENDITURE.
        # UNIT_MEASURE.CURRENCY_DENOM.VALUATION.PRICES.TRANSFORMATION.CUST_BREAKDOWN(market of issue)
        key = ".".join(["Q+A", "N", "+".join(codes), "XW+5Z", "S13+S1311", "S1", "N", "L", "LE",
                        "F3+F3FR+F3VR+F3VRA+F3VRB+F3B", "T+S+L+LS+TT", "_Z", "", "_T+XDC+X1", "N+M+F", "V", "N", "_T+C01+C02"])
        q, a = {}, {}
        for r in _rows(sources.get(f"{BIS}/WS_NA_SEC_DSS/{key}/all?startPeriod={start}&format=csv&detail=dataonly", timeout=120)):
            v = _num(r.get("OBS_VALUE"))
            if v is None:
                continue
            kind = r["UNIT_MEASURE"] if r["UNIT_MEASURE"] in ("USD", "YR") else "LC"
            k = (r["REF_AREA"], r["COUNTERPART_AREA"], r["REF_SECTOR"], r["INSTR_ASSET"], r["MATURITY"], kind,
                 r["CURRENCY_DENOM"], r["VALUATION"], r["CUST_BREAKDOWN"])
            (q if r["FREQ"] == "Q" else a).setdefault(k, {})[r["TIME_PERIOD"]] = v
        time.sleep(2)
        # international bonds (BIS-compiled; the only BIS figures for Egypt and Nigeria), face value, US$ millions
        ikey = ".".join(["Q", "+".join(codes), "3P", "2", "1", "C", "A", "A+F", "TO1", "A", "A+U", "A+C", "A", "A", "I"])
        ids = {}
        for r in _rows(sources.get(f"{BIS}/WS_DEBT_SEC2_PUB/{ikey}/all?startPeriod={start}&format=csv&detail=dataonly", timeout=120)):
            v = _num(r.get("OBS_VALUE"))
            if v is not None:
                ids.setdefault((r["ISSUER_RES"], r["ISSUE_CUR_GROUP"], r["ISSUE_RE_MAT"], r["ISSUE_RATE"]), {})[r["TIME_PERIOD"]] = v
        out = {c: _bis_one(c, q, a, ids) for c in codes}
        out = {c: p for c, p in out.items() if p}
        return out if len(out) >= 25 else None
    return sources.cached("safety_bis", 7 * DAY, fetch, retry=DAY)[0]


def _bis_one(c, q, a, ids):
    p, pick = {}, None
    for sector in ("S13", "S1311"):      # general government, else central government
        for base in ("_T", "C01"):       # all markets, else the domestic market only
            periods = set()
            for val in ("N", "M", "F"):
                periods |= set(q.get((c, "XW", sector, "F3", "T", "USD", "_T", val, base), {}))
            if periods:
                pick = (sector, base, max(periods))
                break
        if pick:
            break
    if pick:
        sector, base, per = pick

        def g(instr="F3", mat="T", cur="_T", val="N", cust=base, cpa="XW", kind="USD"):
            return q.get((c, cpa, sector, instr, mat, kind, cur, val, cust), {}).get(per)

        def share(num, vals=("N", "M", "F")):
            for v in vals:
                n, d = num(v), g(val=v)
                if n is not None and d:
                    return round(100 * n / d, 1)
            return None
        val = next(v for v in ("N", "M", "F") if g(val=v) is not None)
        p.update(period=per, sector="general" if sector == "S13" else "central",
                 domesticOnly=base != "_T", usdBn=round(g(val=val), 1))
        within = lambda v: None if g(mat="S", val=v) is None or g(mat="LS", val=v) is None else g(mat="S", val=v) + g(mat="LS", val=v)
        p["due1y"] = share(within)
        if p["due1y"] is None:
            p["bills"] = share(lambda v: g(mat="S", val=v))     # short-term bills only: a lower bound
        p["variable"] = share(lambda v: g(instr="F3VR", val=v))  # floating plus inflation-linked
        p["linked"] = share(lambda v: g(instr="F3VRA", val=v))
        p["fx"] = share(lambda v: g(cur="X1", val=v))
        p["abroad"] = share(lambda v: g(val=v, cpa="5Z"), vals=("M",))  # held by non-residents, market value

    def la(*k):
        d = a.get((c,) + k, {})
        return (max(d), d[max(d)]) if d else (None, None)
    for v in ("F", "N"):                 # annual table C2: average remaining maturity, central government
        yr, m = la("XW", "S1311", "F3", "TT", "YR", "_T", v, "_T")
        if m is not None:
            p.update(atm=round(m, 1), atmYear=yr)
            break
    if p.get("fx") is None:              # annual table C4: currency of long-term debt
        for sector in ("S13", "S1311"):
            y1, xd = la("XW", sector, "F3", "L", "USD", "XDC", "N", "_T")
            y2, x1 = la("XW", sector, "F3", "L", "USD", "X1", "N", "_T")
            if y1 and y1 == y2 and (xd or 0) + (x1 or 0) > 0:
                p.update(fx=round(100 * x1 / (xd + x1), 1), fxYear=y1)
                break
    if p.get("variable") is None:        # annual table C2: rate mix of central government's long-term debt
        mix = [la("XW", "S1311", i, "L", "USD", "XDC", "F", "_T") for i in ("F3FR", "F3B", "F3VRA")]
        if all(y is not None for y, _ in mix) and len({y for y, _ in mix}) == 1 and sum(x for _, x in mix) > 0:
            tot = sum(x for _, x in mix)
            p.update(variable=round(100 * (mix[1][1] + mix[2][1]) / tot, 1), linked=round(100 * mix[2][1] / tot, 1),
                     variableYear=mix[0][0])
    tot = ids.get((c, "A", "A", "A"), {})
    if tot:
        per = max(tot)
        p["intlUsdBn"], p["intlPeriod"] = round(tot[per] / 1000, 1), per
    return p


# ---------------------------------------------------------------- World Bank: governance and reserves

WB = "https://api.worldbank.org/v2"
ISO3 = {m[0]: m[4] for m in markets.MARKETS} | {m[0]: m[4] for m in monthly_sources.MONTHLY}  # IMF codes are ISO 3166
WGI = {"ge": "GE", "rl": "RL", "cc": "CC", "rq": "RQ", "pv": "PV", "va": "VA"}


def governance():
    """Worldwide Governance Indicators: each market's percentile rank among all economies (0 = worst, 100 = best)
    on six measures, from the estimates for every economy. One slow request, monthly."""
    def fetch(old):
        back = {v: k for k, v in ISO3.items()}
        series = ";".join(f"GOV_WGI_{d}.EST" for d in WGI.values())
        for yr in (date.today().year - 1, date.today().year - 2):
            url = f"{WB}/sources/3/series/{series}/country/all/time/YR{yr}?format=json&per_page=2000"
            est = {}
            for r in json.loads(sources.get(url, timeout=240, tries=2))["source"]["data"]:
                v = {x["concept"]: x["id"] for x in r["variable"]}
                if r.get("value") is not None:
                    est.setdefault(v["Series"].split("_")[-1].split(".")[0], {})[v["Country"]] = r["value"]
            if len(est.get("GE", {})) > 150:
                break
        else:
            return None
        out = {}
        for key, dim in WGI.items():
            vals = est.get(dim) or {}
            n = len(vals)
            for iso, x in vals.items():
                if iso in back and n > 1:
                    out.setdefault(back[iso], {"year": yr})[key] = round(100 * sum(y < x for y in vals.values()) / (n - 1), 1)
        return out if len(out) >= 30 else None
    return sources.cached("safety_wgi", 30 * DAY, fetch, retry=2 * DAY)[0]


def reserves():
    """Foreign-exchange reserves (including gold) in months of imports, latest year. Monthly."""
    def fetch(old):
        y = date.today().year
        back = {v: k for k, v in ISO3.items()}
        url = (f"{WB}/country/{';'.join(v for v in ISO3.values() if v != 'TWN')}/indicator/FI.RES.TOTL.MO"
               f"?format=json&per_page=1000&date={y - 6}:{y}")
        out = {}
        for r in json.loads(sources.get(url, timeout=120, tries=2))[1] or []:
            code = back.get(r["countryiso3code"])
            if code and r["value"] is not None and int(r["date"]) > out.get(code, {}).get("year", 0):
                out[code] = {"months": round(r["value"], 1), "year": int(r["date"])}
        return out if len(out) >= 30 else None
    return sources.cached("safety_reserves", 30 * DAY, fetch, retry=2 * DAY)[0]


# ---------------------------------------------------------------- putting each market's debt profile together

def profile(ecb, bis, fm):
    """One debt profile per market, best source first, each figure with where it came from:
    average maturity: ECB (EU, monthly) > IMF Fiscal Monitor > BIS annual table
    due within a year: ECB > BIS (bonds and bills; for some markets bills only, a lower bound)
    floating or inflation-linked: ECB > BIS;  foreign currency: BIS;  held abroad: IMF > BIS
    financing need: IMF Fiscal Monitor."""
    fmm = (fm or {}).get("markets") or {}
    fm_src = f"IMF Fiscal Monitor ({fm.get('edition', '')})" if fm else ""
    out = {}
    for c in CODES:
        e, b, f = (ecb or {}).get(c) or {}, (bis or {}).get(c) or {}, fmm.get(c) or {}
        p, src = {}, {}

        def put(k, *options):
            for v, s in options:
                if v is not None:
                    p[k], src[k] = v, s
                    return
        put("atm", (e.get("atm"), f"ECB ({e.get('period')})"), (f.get("atm"), fm_src),
            (b.get("atm"), f"BIS, central government ({b.get('atmYear')})"))
        put("due1y", (e.get("due1y"), f"ECB ({e.get('period')})"), (b.get("due1y"), f"BIS ({b.get('period')})"))
        if "due1y" not in p and b.get("bills") is not None and c not in NO_BILLS:
            p["due1y"], p["due1yMin"], src["due1y"] = b["bills"], True, f"BIS, bills only ({b.get('period')})"
        put("floating", (e.get("floating"), f"ECB ({e.get('period')})"),
            (b.get("variable"), f"BIS ({b.get('variableYear') or b.get('period')})"))
        put("fx", (b.get("fx"), f"BIS ({b.get('fxYear') or b.get('period')})"))
        put("abroad", (f.get("abroad"), fm_src), (b.get("abroad"), f"BIS, bonds at market value ({b.get('period')})"))
        put("gfn", (f.get("gfn"), fm_src))
        if b.get("linked") is not None:
            p["linked"] = b["linked"]
        if b.get("usdBn") is not None:
            p["bondsUsdBn"] = b["usdBn"]
        if p:
            p["src"] = src
            p["note"] = NOTES.get(c)
            out[c] = p
    return out


# Hong Kong's government bond figures include the Exchange Fund's own bills (monetary policy paper, not borrowing)
NO_BILLS = {"HK"}
NOTES = {
    "GR": "Most of Greece's debt is cheap, very long-term loans from euro-area governments and the euro rescue funds; "
          "the maturity and rate figures here cover its bonds only.",
    "HK": "Hong Kong's government bonds sit alongside the Exchange Fund's own bills and notes (monetary policy paper), "
          "which are left out here.",
}


def fetch_all():
    """Everything the Safety tab needs beyond the IMF numbers already fetched: {name: {code: ...}}."""
    out, errors = {}, []
    for name, fn in (("ecb", ecb_profile), ("bis", lambda: bis_profile(CODES)), ("wgi", governance), ("reserves", reserves)):
        try:
            out[name] = fn()
        except Exception as e:  # noqa: BLE001 - one source failing shouldn't stop the others
            errors.append(f"safety {name}: {e}")
    fm, dflt = _static("fiscal_monitor.json"), _static("defaults.json")
    out["profile"] = profile(out.get("ecb"), out.get("bis"), fm)
    out["defaults"] = dflt.get("markets") or {}
    wgi_year = next((v.get("year") for v in (out.get("wgi") or {}).values()), None)
    res_year = max((v.get("year") for v in (out.get("reserves") or {}).values()), default=None)
    out["sources"] = {
        "imf": "Debt, deficits, interest, revenue and inflation: IMF World Economic Outlook and Fiscal Monitor.",
        "fiscalMonitor": f"Average maturity (outside the EU), financing need and share held abroad: {fm.get('source')}." if fm else None,
        "ecb": "EU governments' average maturity, share due within a year and floating or inflation-linked share: ECB Data Portal, government finance statistics (monthly).",
        "bis": "Elsewhere, share due within a year, floating or inflation-linked and foreign-currency shares: BIS debt securities statistics (quarterly).",
        "wgi": f"Governance: World Bank Worldwide Governance Indicators ({wgi_year}), percentile rank among all economies." if wgi_year else None,
        "reserves": f"Reserves: World Bank, total reserves in months of imports ({res_year})." if res_year else None,
        "defaults": dflt.get("source"),
    }
    out["sources"] = {k: v for k, v in out["sources"].items() if v}
    out["errors"] = errors
    return out
