"""Bond Compass data: every market's government bonds, curves, public finances and a transparent score.

build() returns everything the page shows; country_history() returns one market's long yield history
for its detail panel. All yields are in % a year; spreads and changes are in basis points (bp, 0.01%).
"""
import math
import statistics as st
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone

import bondmath
import markets
import snapshot
import sources

DAY = 86400
TENOR_WORD = lambda t: f"{t[:-1]}-month" if t.endswith("M") else f"{t[:-1]}-year"

# Score recipe: each ingredient is ranked 0-100 across all markets, then weighted. Value looks at what the
# bond pays; safety at the government behind it. Every ingredient is shown on the page.
WEIGHTS = {
    "realY": 0.25,   # benchmark yield minus the IMF's inflation forecast (higher = better)
    "carry": 0.20,   # how far yields could rise in a year before the bond does worse than cash (higher = better)
    "cheap": 0.15,   # where today's yield sits in its own 3-year range (higher yield = cheaper = better)
    "rating": 0.15,  # average of the S&P, Moody's and Fitch ratings (higher = better)
    "debt": 0.10,    # government debt as a share of the economy (lower = better)
    "gap": 0.10,     # how far the budget falls short of keeping debt steady at today's borrowing cost (lower = better)
    "intRev": 0.05,  # share of government revenue spent on interest (lower = better)
}
VALUE_PARTS, SAFETY_PARTS = ("realY", "carry", "cheap"), ("rating", "debt", "gap", "intRev")
HIGHER_IS_BETTER = {"realY": True, "carry": True, "cheap": True, "rating": True, "debt": False, "gap": False,
                    "intRev": False}

# ---------------------------------------------------------------- ratings scale
SP = ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-", "B+", "B", "B-",
      "CCC+", "CCC", "CCC-", "CC", "C", "SD", "D"]
MOODYS = ["Aaa", "Aa1", "Aa2", "Aa3", "A1", "A2", "A3", "Baa1", "Baa2", "Baa3", "Ba1", "Ba2", "Ba3", "B1", "B2",
          "B3", "Caa1", "Caa2", "Caa3", "Ca", "C"]


def notch(r, scale):
    """AAA/Aaa = 21 down to D/C = 0; None if unrated."""
    r = (r or "").split()[0].replace("−", "-") if r else ""
    return 21 - scale.index(r) if r in scale else None


def rating_block(rt):
    if not rt:
        return None
    parts = {}
    for k, scale in (("sp", SP), ("moodys", MOODYS), ("fitch", SP)):
        a = rt.get(k)
        if a:
            n = notch(a["r"], scale)
            parts[k] = {"r": a["r"], "o": a.get("o"), "d": a.get("d"), "n": n}
    ns = [p["n"] for p in parts.values() if p["n"] is not None]
    if not ns:
        return None
    avg = sum(ns) / len(ns)
    tilt = sum(0.33 if (p.get("o") or "").lower().startswith("pos") else -0.33 if (p.get("o") or "").lower().startswith("neg")
               else 0 for p in parts.values()) / len(parts)
    label = SP[max(0, min(len(SP) - 1, 21 - round(avg)))]
    return {**parts, "avg": round(avg, 2), "score": round(avg + tilt, 2), "label": label,
            "ig": avg >= 11.5, "tilt": tilt}


# ---------------------------------------------------------------- helpers

def pct_rank(values):
    idx = sorted((i for i, v in enumerate(values) if v is not None), key=lambda i: values[i])
    out, n = [None] * len(values), len(idx)
    for r, i in enumerate(idx):
        out[i] = 100 * r / (n - 1) if n > 1 else 50.0
    return out


def signal(s):
    return (None if s is None else "Strong overweight" if s >= 80 else "Overweight" if s >= 60
            else "Neutral" if s >= 40 else "Underweight" if s >= 20 else "Avoid")


def at_or_before(series, ts):
    """Value of a [[t, v], ...] series on or just before ts (None if the series starts later)."""
    lo, hi = 0, len(series)
    while lo < hi:
        mid = (lo + hi) // 2
        if series[mid][0] <= ts:
            lo = mid + 1
        else:
            hi = mid
    return series[lo - 1][1] if lo else None


def weekly(series, since=None):
    """Last value of each week (and always the final point), optionally only from `since`."""
    out, last_wk = [], None
    for t, v in series:
        if since and t < since:
            continue
        wk = (t // DAY + 3) // 7
        if out and wk == last_wk:
            out[-1] = [t, v]
        else:
            out.append([t, v])
        last_wk = wk
    return out


def thin(series, daily_from):
    """Daily points from daily_from onwards, weekly before: keeps long histories small."""
    return weekly([p for p in series if p[0] < daily_from]) + [p for p in series if p[0] >= daily_from]


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def bp(a, b):
    return None if a is None or b is None else round((a - b) * 100, 1)


def yield_stats(h, y, now):
    """Changes (bp) and where today's yield sits in its own past, from a daily history h = [[t, y]]."""
    if not h:
        return {}
    ago = lambda days: at_or_before(h, now - days * DAY)
    jan1 = int(datetime(date.fromtimestamp(now).year, 1, 1, tzinfo=timezone.utc).timestamp()) - 1
    yr = [v for t, v in h if t >= now - 365 * DAY] + [y]
    y3 = [v for t, v in h if t >= now - 3 * 365 * DAY] + [y]
    y5 = [v for t, v in h if t >= now - 5 * 365 * DAY] + [y]
    recent = [v for t, v in h if t >= now - 92 * DAY]
    diffs = [b - a for a, b in zip(recent, recent[1:])]
    sd = st.pstdev(yr) if len(yr) > 20 else None
    return {
        "d1w": bp(y, ago(7)), "d1m": bp(y, ago(30)), "d3m": bp(y, ago(91)), "ytd": bp(y, at_or_before(h, jan1)),
        "d1y": bp(y, ago(365)), "d3y": bp(y, ago(3 * 365)),
        "hi1y": max(yr), "lo1y": min(yr), "avg1y": round(mean(yr), 3),
        "z1y": round((y - mean(yr)) / sd, 2) if sd else None,
        "pct3y": round(100 * sum(v < y for v in y3) / len(y3)) if len(y3) > 250 else None,
        "pct5y": round(100 * sum(v < y for v in y5) / len(y5)) if len(y5) > 500 else None,
        "avg5y": round(mean(y5), 3) if len(y5) > 500 else None,
        "vol": round(st.pstdev(diffs) * math.sqrt(252) * 100) if len(diffs) > 30 else None,  # bp a year
        "since": h[0][0],
    }


def approx_return(h, y_now, now, yrs, start):
    """Total return of a constant-maturity bond from `start` to now, rebuilt from daily yields:
    each day earns its yield, and loses (gains) duration x the rise (fall) in yield, plus convexity."""
    pts = [p for p in h if p[0] >= start - 6 * DAY]
    pts = [p for p in pts if p[0] < now - DAY / 2] + [[now, y_now]]
    if len(pts) < 20 or pts[0][0] > start + 10 * DAY:
        return None
    growth = 1.0
    for (t0, a), (t1, b) in zip(pts, pts[1:]):
        if t0 < start:
            continue
        mod, conv = bondmath.par_duration(a, yrs)
        dy = (b - a) / 100
        growth *= 1 + a / 100 * (t1 - t0) / (365 * DAY) - mod * dy + 0.5 * conv * dy * dy
    return growth - 1


def fx_ratio(fx, ccy, start, end):
    """How much one unit of `ccy` gained in pounds between two dates (fraction), from Yahoo rates per US dollar."""
    if ccy == "GBP":
        return 0.0
    g = fx.get("GBP=X")
    if not g:
        return None
    gs = list(zip(g["t"], g["c"]))
    gbp_per_usd = lambda t: at_or_before(gs, t)
    if ccy == "USD":
        per = gbp_per_usd
    else:
        l = fx.get(f"{ccy}=X")
        if not l:
            return None
        ls = list(zip(l["t"], l["c"]))
        per = lambda t: (gbp_per_usd(t) / at_or_before(ls, t)) if gbp_per_usd(t) and at_or_before(ls, t) else None
    a, b = per(start), per(end)
    return b / a - 1 if a and b else None


def policy_block(series, now):
    if not series:
        return None
    rate, moves = series[-1][1], []
    for (t0, a), (t1, b) in zip(series, series[1:]):
        if abs(b - a) > 1e-9:
            moves.append({"t": t1, "from": a, "to": b})
    last = moves[-1] if moves else None
    yr_ago = at_or_before(series, now - 365 * DAY)
    m3 = [x for x in moves if x["t"] >= now - 92 * DAY]
    return {"rate": rate, "asOf": series[-1][0], "last": last, "d1y": bp(rate, yr_ago),
            "moves3m": round(sum(x["to"] - x["from"] for x in m3) * 100), "n3m": len(m3),
            "series": [[t, v] for t, v in weekly(series, now - 2 * 365 * DAY)]}


# ---------------------------------------------------------------- the build

def _try(fn, *a):
    try:
        return fn(*a), None
    except Exception as e:  # noqa: BLE001 - one source failing shouldn't take the page down
        return None, f"{fn.__name__}: {e}"


def fetch_everything():
    mk = markets.MARKETS
    pts = {m[0]: markets.points(m) for m in mk}
    all_syms = [s for p in pts.values() for _, s, _ in p]
    hist_syms = [s for p in pts.values() for _, s, h in p if h]
    ccys = sorted({m[3] for m in mk} - {"USD"})
    names = {markets.RATING_NAME.get(m[0], m[1]) for m in mk}
    with ThreadPoolExecutor(max_workers=7) as ex:
        jobs = {
            "quotes": ex.submit(_try, sources.quotes, all_syms),
            "history": ex.submit(_try, sources.history, hist_syms),
            "fred": ex.submit(_try, sources.fred, [f[0] for f in markets.FRED]),
            "imf": ex.submit(_try, sources.imf, list(markets.IMF), [m[4] for m in mk]),
            "bis": ex.submit(_try, sources.policy_rates, sorted({m[5] for m in mk if m[5]})),
            "yahoo": ex.submit(_try, sources.yahoo_all, markets.YAHOO + [f"{c}=X" for c in ccys if c != "GBP"]),
            "ratings": ex.submit(_try, sources.ratings, names),
        }
        got = {k: j.result() for k, j in jobs.items()}
    errors = [e for _, e in got.values() if e]
    return {k: v for k, (v, _) in got.items()}, errors, pts


def build():
    raw, errors, pts = fetch_everything()
    Q = raw["quotes"] or {}
    H = dict(raw["history"] or {})
    for sym, own in snapshot.load().items():  # our own daily closes fill in maturities CNBC keeps no history for
        if not H.get(sym) and len(own) >= 2:
            H[sym] = own
    fred, fred_at = raw["fred"] or ({}, None)
    imf, imf_at = raw["imf"] or ({}, None)
    bis, bis_at = raw["bis"] or ({}, None)
    fx = raw["yahoo"] or {}
    rts = (raw["ratings"] or {}).get("ratings", {})
    rts_checked = (raw["ratings"] or {}).get("checked")
    now = time.time()
    today = date.today()
    year = today.year

    # ---------- pass 1: each market's quotes, curve and history
    rows = []
    for m in markets.MARKETS:
        code, name, region, ccy, imf_code, bis_code, freq, _, _, ll = m
        bonds = []
        for tenor, sym, has_hist in pts[code]:
            q, h = Q.get(sym), H.get(sym)
            if not q and not h:
                continue
            if q:
                y, chg, when = q["y"], q["chg"], q["time"]
            else:  # no live quote: fall back to the last close in the history
                y, when = h[-1][1], h[-1][0] + DAY * 0.75
                chg = (h[-1][1] - h[-2][1]) if len(h) > 1 else None
            mat = None
            if q and q.get("mat"):
                try:
                    mat = date.fromisoformat(q["mat"])
                except ValueError:
                    mat = None
            nominal = markets.tenor_years(tenor)
            if mat is None or mat <= today or abs((mat - today).days / 365.25 - nominal) > max(2.5, nominal * 0.5):
                mat = date.fromordinal(today.toordinal() + round(nominal * 365.25))
                coupon = None if nominal <= 1 else (q or {}).get("coupon")
                approx_mat = True
            else:
                coupon, approx_mat = (q or {}).get("coupon"), False
            bonds.append({"tenor": tenor, "sym": sym, "hist": bool(h), "y": y, "chg": None if chg is None else round(chg * 100, 1),
                          "coupon": coupon, "mat": mat.isoformat(), "approxMat": approx_mat,
                          "quoted": (q or {}).get("price"), "time": when, "stale": bool(when and now - when > 5 * DAY),
                          "_h": h, "_mat": mat})
        if not bonds:
            continue
        # curve: drop quotes that sit far off the line through their neighbours
        order = sorted(range(len(bonds)), key=lambda i: (bonds[i]["_mat"] - today).days)
        cpts = [((bonds[i]["_mat"] - today).days / 365.25, bonds[i]["y"]) for i in order]
        for j in bondmath.outliers(cpts):
            bonds[order[j]]["outlier"] = True
        bonds = [bonds[i] for i in order]
        rows.append({"code": code, "name": name, "region": region, "ccy": ccy, "iso": markets.ISO.get(code), "ll": ll,
                     "dm": code in markets.DEVELOPED, "euro": code in markets.EURO, "freq": freq,
                     "_imf": imf_code, "_bis": bis_code, "bonds": bonds})

    curve_now = {r["code"]: bondmath.Curve([((b["_mat"] - today).days / 365.25, b["y"]) for b in r["bonds"]
                                             if not b.get("outlier")]) for r in rows}

    # ---------- pass 2: cash rates, so carry and currency hedging can be worked out
    for r in rows:
        pol = policy_block(bis.get(r["_bis"]), now) if r["_bis"] else None
        if pol:
            pol["bank"] = r["_bis"]  # euro-area markets share the ECB
        bill = next((b for b in r["bonds"] if markets.tenor_years(b["tenor"]) <= 1 and not b.get("outlier")), None)
        if pol:
            r["cash"] = {"rate": pol["rate"], "src": "policy"}
        elif bill:
            r["cash"] = {"rate": bill["y"], "src": "bill", "tenor": bill["tenor"]}
        else:
            r["cash"] = None
        r["policy"] = pol
    cash = {r["code"]: (r["cash"] or {}).get("rate") for r in rows}
    gb_cash, us_cash = cash.get("GB"), cash.get("US")

    # ---------- pass 3: public finances (IMF)
    def imf_series(ind, c):
        return (imf.get(ind) or {}).get(c) or {}

    for r in rows:
        c = r["_imf"]
        g = lambda ind, yr=year: imf_series(ind, c).get(yr)
        fwd = lambda ind: [imf_series(ind, c).get(y) for y in range(year + 1, year + 6)]
        infl_f = [v for v in fwd("PCPIPCH") if v is not None]
        grow_f = [v for v in fwd("NGDP_RPCH") if v is not None]
        nominal_g = [((1 + a / 100) * (1 + b / 100) - 1) * 100 for a, b in zip(fwd("NGDP_RPCH"), fwd("PCPIPCH"))
                     if a is not None and b is not None]
        debt, primary, balance, revenue = g("GGXWDG_NGDP"), g("GGXONLB_G01_GDP_PT"), g("GGXCNL_G01_GDP_PT"), g("GGR_G01_GDP_PT")
        if balance is None:
            balance = g("GGXCNL_NGDP")
        interest = primary - balance if primary is not None and balance is not None else None
        path = imf_series("GGXWDG_NGDP", c)
        r["fiscal"] = {
            "year": year, "debt": debt, "netDebt": g("GGXWDN_G01_GDP_PT"), "balance": balance, "primary": primary,
            "interest": round(interest, 2) if interest is not None else None, "revenue": revenue,
            "intRev": round(100 * interest / revenue, 1) if interest is not None and revenue else None,
            "effRate": round(100 * interest / debt, 2) if interest is not None and debt else None,
            "growth": g("NGDP_RPCH"), "inflation": g("PCPIPCH"), "current": g("BCA_NGDPD"),
            "unemployment": g("LUR"), "gdpUsd": g("NGDPD"),
            "inflFwd": round(mean(infl_f), 2) if infl_f else None, "inflNext": infl_f[0] if infl_f else None,
            "inflPath": infl_f, "growthFwd": round(mean(grow_f), 2) if grow_f else None,
            "nomGrowth": round(mean(nominal_g), 2) if nominal_g else None,
            "debtIn5y": path.get(year + 5), "debtPath": [[y, round(v, 1)] for y, v in sorted(path.items()) if year - 12 <= y <= year + 6],
            "deficitPath": [[y, round(v, 2)] for y, v in sorted(imf_series("GGXCNL_G01_GDP_PT", c).items()) if year - 12 <= y <= year + 6],
            "primaryPath": [[y, round(v, 2)] for y, v in sorted(imf_series("GGXONLB_G01_GDP_PT", c).items()) if year - 12 <= y <= year + 6],
        }
        rt = rating_block(rts.get(markets.RATING_NAME.get(r["code"], r["name"])))
        r["rating"] = rt

    # ---------- pass 4: every bond's price, risk, carry, real yield, spreads and history
    for r in rows:
        crv, fis = curve_now[r["code"]], r["fiscal"]
        my_cash = cash.get(r["code"])
        for b in r["bonds"]:
            a = bondmath.analytics(b["y"], b["coupon"], b["_mat"], r["freq"], today)
            if not a:
                continue
            yrs, mod = a["yrs"], a["mod"]
            b.update({"yrs": round(yrs, 2), "price": round(a["clean"], 3), "dirty": round(a["dirty"], 3),
                      "accrued": round(a["accrued"], 3), "mac": round(a["mac"], 2), "mod": round(mod, 2),
                      "conv": round(a["conv"], 2), "dv01": round(a["dv01"])})
            q = b.pop("quoted")
            if q and abs(q / a["clean"] - 1) < 0.03:
                b["price"], b["priceSrc"] = q, "quote"
            # roll-down: the yield the same bond would have one year from now if the curve stayed put
            roll = None
            if yrs > 1.25 and not b.get("outlier") and crv.covers(yrs - 1, 0.1):
                roll = b["y"] - crv.at(yrs - 1)
            ret12 = b["y"] + (mod * roll if roll is not None else 0)
            b["roll"] = bp(roll, 0) if roll is not None else None
            b["ret12"] = round(ret12, 3)
            b["excess"] = round(ret12 - my_cash, 3) if my_cash is not None else None
            b["breakeven"] = round(b["excess"] / max(mod, 0.25) * 100) if b["excess"] is not None and yrs > 0.75 else None
            # yield hedged into pounds or dollars: earn the bond's yield, swap the currency back at the
            # forward rate, which costs (or pays) the difference between the two short-term interest rates
            b["hedgedGbp"] = round(b["y"] + gb_cash - my_cash, 3) if None not in (gb_cash, my_cash) else None
            b["hedgedUsd"] = round(b["y"] + us_cash - my_cash, 3) if None not in (us_cash, my_cash) else None
            n_years = min(5, max(1, round(yrs)))
            infl = mean(fis["inflPath"][:n_years]) if fis["inflPath"] else None
            b["realY"] = round(b["y"] - infl, 3) if infl is not None else None
            for k, ref in (("vsUS", "US"), ("vsDE", "DE"), ("vsGB", "GB")):
                c2 = curve_now.get(ref)
                b[k] = bp(b["y"], c2.at(yrs)) if c2 and c2.covers(yrs) and r["code"] != ref else (0.0 if r["code"] == ref else None)
            if b["_h"]:
                b.update(yield_stats(b["_h"], b["y"], now))

    # ---------- pass 5: each market's benchmark, curve shape, returns and score inputs
    for r in rows:
        bs = [b for b in r["bonds"] if "mod" in b]
        r["bonds"] = bs
        if not bs:
            continue
        # slopes and the market's rate expectations compare maturity buckets (the "10-year" is the current
        # 10-year benchmark even if it matures in 8.4 years), the way they're quoted in the market
        crv = bondmath.Curve([(markets.tenor_years(b["tenor"]), b["y"]) for b in bs if not b.get("outlier")])
        bench = min((b for b in bs if not b.get("outlier")), key=lambda b: (abs(markets.tenor_years(b["tenor"]) - 10), not b["hist"]),
                    default=bs[-1])
        r["bench"] = bench["tenor"]
        y_at = lambda x: crv.at(x) if crv.covers(x, min(0.75, x * 0.5)) else None
        s = {"s2s10": bp(y_at(10), y_at(2)), "s5s30": bp(y_at(30), y_at(5)), "s3m10": bp(y_at(10), y_at(0.25)),
             "s10s30": bp(y_at(30), y_at(10)),
             "fly": round((2 * y_at(5) - y_at(2) - y_at(10)) * 100, 1) if None not in (y_at(2), y_at(5), y_at(10)) else None}
        r["slopes"] = s
        lead = s["s2s10"] if s["s2s10"] is not None else s["s3m10"]
        r["shape"] = (None if lead is None else "Inverted" if lead < -10 else "Flat" if lead < 25 else
                      "Steep" if lead > 150 else "Upward-sloping")
        if s["fly"] is not None and s["fly"] > 25 and (lead or 0) < 25:
            r["shape"] = "Humped"
        # the curve one week, one month, three months and one year ago (maturities with a history only)
        snaps = {}
        for k, days in (("w1", 7), ("m1", 30), ("m3", 91), ("y1", 365)):
            cpts = [(markets.tenor_years(b["tenor"]), at_or_before(b["_h"], now - days * DAY)) for b in bs if b["hist"] and not b.get("outlier")]
            cpts = [p for p in cpts if p[1] is not None]
            if len(cpts) >= 2:
                snaps[k] = [[round(x, 3), y] for x, y in cpts]
        r["curve"] = {"now": [[b["yrs"], b["y"]] for b in bs if not b.get("outlier")], **snaps}
        # slope changes over a month, from the history of the same maturities
        h2, h10 = next((b for b in bs if b["tenor"] == "2Y" and b["hist"]), None), next((b for b in bs if b["tenor"] == "10Y" and b["hist"]), None)
        if h2 and h10:
            then = lambda days: bp(at_or_before(h10["_h"], now - days * DAY), at_or_before(h2["_h"], now - days * DAY))
            r["slopes"]["s2s10_1m"] = then(30)
            r["slopes"]["s2s10_1y"] = then(365)
        # market's view of rates: how far the 2-year yield sits above (hikes priced) or below (cuts) cash
        two = y_at(2)
        r["expects"] = bp(two, cash.get(r["code"])) if two is not None and cash.get(r["code"]) is not None else None
        # approximate total returns of the benchmark (constant maturity), local currency and in pounds
        tr = {}
        if bench["hist"]:
            jan1 = int(datetime(today.year, 1, 1, tzinfo=timezone.utc).timestamp())
            for k, start in (("y1", now - 365 * DAY), ("ytd", jan1), ("m3", now - 91 * DAY)):
                loc = approx_return(bench["_h"], bench["y"], now, markets.tenor_years(bench["tenor"]), start)
                f = fx_ratio(fx, r["ccy"], start, now)
                tr[k] = {"local": loc, "fx": f, "gbp": (1 + loc) * (1 + f) - 1 if loc is not None and f is not None else None}
                pol, gpol = r.get("policy"), next((x.get("policy") for x in rows if x["code"] == "GB"), None)
                if loc is not None and pol and gpol:
                    yrs_frac = (now - start) / (365 * DAY)
                    diff = mean([v for t, v in pol["series"] if t >= start]) or pol["rate"]
                    gdiff = mean([v for t, v in gpol["series"] if t >= start]) or gpol["rate"]
                    tr[k]["hedged"] = loc + (gdiff - diff) / 100 * yrs_frac
            r["spark"] = [v for _, v in weekly(bench["_h"], now - 365 * DAY)] + [bench["y"]]
        r["tr"] = tr
        fis = r["fiscal"]
        y10 = bench["y"]
        if fis["nomGrowth"] is not None and fis["debt"] is not None:
            rg = y10 - fis["nomGrowth"]
            need = rg / (100 + fis["nomGrowth"]) * fis["debt"]  # primary balance that holds debt/GDP steady
            fis.update(rMinusG=round(rg, 2), pbNeeded=round(need, 2),
                       gap=round(need - fis["primary"], 2) if fis["primary"] is not None else None)
        fis["refi"] = round(y10 - fis["effRate"], 2) if fis.get("effRate") is not None else None
        r["_inputs"] = {
            "realY": bench.get("realY"), "carry": bench.get("breakeven"),
            "cheap": bench.get("pct3y"),
            "rating": (r["rating"] or {}).get("score"), "debt": fis["debt"], "gap": fis.get("gap"),
            "intRev": fis["intRev"],
        }

    rows = [r for r in rows if r.get("bench")]
    # ---------- the score
    ranks = {}
    for k in WEIGHTS:
        vals = [r["_inputs"][k] for r in rows]
        if not HIGHER_IS_BETTER[k]:
            vals = [None if v is None else -v for v in vals]
        ranks[k] = pct_rank(vals)
    for i, r in enumerate(rows):
        parts = {k: None if ranks[k][i] is None else round(ranks[k][i]) for k in WEIGHTS}
        blend = lambda keys: (lambda w: round(sum(parts[k] * WEIGHTS[k] for k in keys if parts[k] is not None) / w, 1) if w else None)(
            sum(WEIGHTS[k] for k in keys if parts[k] is not None))
        score = blend(list(WEIGHTS))
        r["m"] = {"score": score, "value": blend(VALUE_PARTS), "safety": blend(SAFETY_PARTS), "parts": parts,
                  "inputs": r.pop("_inputs"), "signal": signal(score)}

    for r in rows:
        for b in r["bonds"]:
            b.pop("_h", None), b.pop("_mat", None)
        r.pop("_imf"), r.pop("_bis")

    credit = credit_block(fred, now)
    move = fx.get("^MOVE")
    move_b = None
    if move:
        ms = list(zip(move["t"], move["c"]))
        last = ms[-1][1]
        yr = [v for t, v in ms if t >= now - 365 * DAY]
        move_b = {"last": last, "d1m": last - (at_or_before(ms, now - 30 * DAY) or last), "hi1y": max(yr), "lo1y": min(yr),
                  "pct": round(100 * sum(v < last for v in [v for _, v in ms]) / len(ms)),
                  "series": weekly([[t, v] for t, v in ms]), "time": move["time"]}
    times = [b["time"] for r in rows for b in r["bonds"] if b.get("time") and not b["stale"]]
    out = {
        "generated": now, "marketTime": max(times) if times else now, "rows": rows,
        "credit": credit, "move": move_b, "weights": WEIGHTS,
        "rules": backdrop(rows, credit, move_b),
        "sources": {"imfAt": imf_at, "fredAt": fred_at, "bisAt": bis_at, "ratingsChecked": rts_checked,
                    "imfYear": year},
        "errors": errors + [f"no quote: {s}" for r in markets.MARKETS for _, s, _ in pts[r[0]] if s not in Q and s not in H][:40],
    }
    return out


def credit_block(fred, now):
    out = []
    for sid, label, group, kind in markets.FRED:
        s = fred.get(sid)
        if not s:
            continue
        last_t, last = s[-1]
        unit = 100 if kind == "spread" else 1  # spreads are shown in bp
        ago = lambda d: at_or_before(s, now - d * DAY)
        diff = lambda old: None if old is None else round((last - old) * 100, 1)
        vals = [v for _, v in s]
        out.append({"id": sid, "label": label, "group": group, "kind": kind, "last": round(last * unit, 2), "asOf": last_t,
                    "d1w": diff(ago(7)), "d1m": diff(ago(30)), "d3m": diff(ago(91)), "d1y": diff(ago(365)),
                    "pct": round(100 * sum(v < last for v in vals) / len(vals)), "since": s[0][0],
                    "lo": round(min(vals) * unit, 2), "hi": round(max(vals) * unit, 2), "avg": round(mean(vals) * unit, 2),
                    "series": [[t, round(v * unit, 3)] for t, v in weekly(s)]})
    return out


def backdrop(rows, credit, move):
    """Today's bond-market backdrop as plain-English rules: transparent thresholds, not a forecast."""
    rules = []

    def rule(name, tone, note, active=True):
        rules.append({"name": name, "tone": tone, "note": note, "active": active})

    bench = lambda r: next(b for b in r["bonds"] if b["tenor"] == r["bench"])
    dm = [r for r in rows if r["dm"]]
    m1 = [bench(r).get("d1m") for r in dm if bench(r).get("d1m") is not None]
    if m1:
        med = st.median(m1)
        up = sum(v > 0 for v in m1)
        if med >= 15:
            rule("Yields rising", "neg", f"The typical developed-market 10-year yield is up {med:.0f}bp over the past month ({up} of {len(m1)} rose). Rising yields mean falling bond prices: longer bonds lose most.")
        elif med <= -15:
            rule("Yields falling", "pos", f"The typical developed-market 10-year yield is down {abs(med):.0f}bp over the past month ({len(m1) - up} of {len(m1)} fell). Falling yields lift bond prices, most of all for longer bonds.")
        else:
            rule("Yields steady", "info", f"The typical developed-market 10-year yield moved {med:+.0f}bp over the past month: no strong trend (the rule needs a 15bp move).", False)
    sl = [r["slopes"].get("s2s10_1m") for r in dm]
    now_sl = [r["slopes"].get("s2s10") for r in dm]
    pairs = [(a, b) for a, b in zip(now_sl, sl) if a is not None and b is not None]
    if pairs:
        chg = st.median([a - b for a, b in pairs])
        inv = sum(a < 0 for a, _ in pairs)
        if chg >= 10:
            rule("Curves steepening", "info", f"The gap between 10-year and 2-year yields has widened by a typical {chg:.0f}bp over the month. Long bonds are falling behind short ones; usually a sign of worries about inflation or government borrowing, or of rate cuts ahead.")
        elif chg <= -10:
            rule("Curves flattening", "info", f"The gap between 10-year and 2-year yields has narrowed by a typical {abs(chg):.0f}bp over the month. Short yields are rising faster than long ones (or falling more slowly); often a sign that markets expect central banks to keep rates high.")
        else:
            rule("Curve shape", "info", f"The 10-year minus 2-year gap is little changed over the month ({chg:+.0f}bp). {inv} of {len(pairs)} developed-market curves are inverted (2-year above 10-year).", False)
    hy = next((c for c in credit if c["id"] == "BAMLH0A0HYM2"), None)
    if hy:
        if hy["pct"] <= 20:
            rule("Credit priced for calm", "warn", f"US high-yield bonds pay just {hy['last']:.0f}bp more than Treasuries, tighter than {100 - hy['pct']}% of days in the past {round((time.time() - hy['since']) / 31557600)} years. Investors are being paid little for default risk; little cushion if the economy turns.")
        elif hy["pct"] >= 80:
            rule("Credit under stress", "neg", f"US high-yield bonds pay {hy['last']:.0f}bp more than Treasuries, wider than {hy['pct']}% of days in the past {round((time.time() - hy['since']) / 31557600)} years: investors are demanding more for default risk.")
        else:
            rule("Credit spreads", "info", f"US high-yield bonds pay {hy['last']:.0f}bp more than Treasuries, in the middle of their recent range.", False)
    if move:
        v = move["last"]
        if v >= 120:
            rule("Bond market jumpy", "neg", f"The MOVE index (expected swings in US Treasury yields) is {v:.0f}, above 120: big daily moves are likely, so size positions with care.")
        elif v <= 80:
            rule("Bond market calm", "pos", f"The MOVE index (expected swings in US Treasury yields) is a calm {v:.0f} (80 or below).")
        else:
            rule("Bond volatility", "info", f"The MOVE index (expected swings in US Treasury yields) is {v:.0f}: normal (calm is 80 or below, stressed 120 or above).", False)
    ff = next((c for c in credit if c["id"] == "T5YIFR"), None)
    if ff:
        v = ff["last"]
        if v >= 2.6:
            rule("Inflation worries", "neg", f"Markets expect US inflation to average {v:.2f}% in the five years starting five years from now, above the Fed's 2% target by a margin (the rule needs 2.6%). That pushes long-term yields up.")
        elif v <= 2.0:
            rule("Inflation expectations low", "pos", f"Markets expect US inflation to average {v:.2f}% in the five years starting five years from now: at or below the Fed's 2% target.")
        else:
            rule("Inflation expectations", "info", f"Markets expect US inflation to average {v:.2f}% in the five years starting five years from now: close to normal (the Fed targets 2%; this gauge has usually sat at 2.0-2.6%).", False)
    pol = list({r["policy"]["bank"]: r["policy"] for r in rows if r.get("policy")}.values())
    hikes = sum(1 for p in pol if p["moves3m"] > 0)
    cuts = sum(1 for p in pol if p["moves3m"] < 0)
    if hikes or cuts:
        tone = "neg" if hikes > cuts else "pos" if cuts > hikes else "info"
        rule("Central banks " + ("tightening" if hikes > cuts else "easing" if cuts > hikes else "split"), tone,
             f"In the past 3 months {hikes} of the {len(pol)} central banks followed here raised interest rates and {cuts} cut them. "
             + ("Rate rises push short-term yields up most." if hikes > cuts else "Rate cuts pull short-term yields down most." if cuts > hikes else ""))
    return rules


def country_history(code):
    """One market's long yield history: daily for the last two years, weekly before (since 2016)."""
    m = next(x for x in markets.MARKETS if x[0] == code)
    H = dict(sources.history([s for x in markets.MARKETS for _, s, h in markets.points(x) if h]))  # same list as build(), so it hits the cache
    for sym, own in snapshot.load().items():
        if not H.get(sym) and len(own) >= 2:
            H[sym] = own
    since = time.time() - 2 * 365 * DAY
    return {"code": code, "series": {t: thin(H[s], since) for t, s, _ in markets.points(m) if H.get(s)}}
