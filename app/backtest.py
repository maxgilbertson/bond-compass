"""The score tested on the past: every month since 2016, rebuild the parts of the score that can be
rebuilt from data as it stood then, rank the markets, and see how the top and bottom fifth did next month.

What can be rebuilt (75% of the live score's weight):
  real yield     10-year yield minus the previous calendar year's actual inflation (IMF), known at the time
  cushion        (yield + roll-down - cash rate) / duration, from that day's curve and policy rate (BIS)
  cheapness      where the 10-year yield sat in its own previous 3 years
  debt           government debt / GDP for the previous year (IMF actual)
  interest bill  net interest / revenue for the previous year (IMF actual)
What can't: credit ratings and the budget gap, because the ratings table and IMF forecasts aren't kept
as they stood on past dates. They're left out and the rest re-weighted, exactly as the live score does
when an ingredient is missing.

Returns are what a pound-based investor would have earned holding each market's 10-year bond with the
currency hedged back to pounds (perf.index), so markets are compared like for like.
"""
import math
import statistics as st
from datetime import datetime, timezone

import bondmath
import markets
import perf

PARTS = {"realY": 0.25, "carry": 0.20, "cheap": 0.15, "debt": 0.10, "intRev": 0.05}
LOWER_BETTER = {"debt", "intRev"}
COST = 0.0005
DAY = 86400


def month_ends(t0, t1):
    out = []
    d = datetime.fromtimestamp(t0, timezone.utc)
    y, m = d.year, d.month
    while True:
        y2, m2 = (y + 1, 1) if m == 12 else (y, m + 1)
        end = datetime(y2, m2, 1, tzinfo=timezone.utc).timestamp() - 1
        if end > t1:
            return out
        out.append(int(end))
        y, m = y2, m2


def pct_rank(values):
    idx = sorted((i for i, v in enumerate(values) if v is not None), key=lambda i: values[i])
    out, n = [None] * len(values), len(idx)
    for r, i in enumerate(idx):
        out[i] = r / (n - 1) if n > 1 else 0.5
    return out


def spearman(xs, ys):
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pairs) < 6:
        return None
    rx, ry = pct_rank([p[0] for p in pairs]), pct_rank([p[1] for p in pairs])
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sxx = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return sxy / sxx if sxx else None


def tstat(xs):
    xs = [x for x in xs if x is not None]
    if len(xs) < 3:
        return None
    sd = st.stdev(xs)
    return sum(xs) / len(xs) / (sd / math.sqrt(len(xs))) if sd else None


def run(H, imf, cash_daily, cash_monthly, now, only=None):
    """H: {symbol: cleaned daily yields}; imf: {indicator: {imf code: {year: value}}};
    cash_daily / cash_monthly: {BIS code: [[t, rate]]}; only: a set of market codes to restrict the test to."""
    cash_gb = perf.rate_fn(cash_daily.get("GB"), cash_monthly.get("GB"))
    univ = []
    for m in markets.MARKETS:
        code, bis, imf_code = m[0], m[5], m[4]
        if only and code not in only:
            continue
        pts = [(markets.tenor_years(t), H.get(s)) for t, s, _ in markets.points(m)]
        pts = [(x, h, [p[0] for p in h]) for x, h in pts if h]
        ten = next(((h, ts) for x, h, ts in pts if x == 10), None)
        if not ten:
            continue
        if bis:
            cash = perf.rate_fn(cash_daily.get(bis), cash_monthly.get(bis))
        else:
            bill = next((h for x, h, _ in pts if x <= 1), None)
            cash = perf.rate_fn(bill) if bill else (lambda t: None)
        univ.append({"code": code, "imf": imf_code, "ten": ten, "curve": pts, "cash": cash})
    if not univ:
        return None
    start = max(min(u["ten"][0][0][0] for u in univ) + 365 * DAY, datetime(2017, 1, 1, tzinfo=timezone.utc).timestamp())
    ends = month_ends(start, now)
    get = lambda ind, c, yr: ((imf.get(ind) or {}).get(c) or {}).get(yr)
    months, comp_ic = [], {k: [] for k in PARTS}
    held = {"top": None, "bottom": None}
    for t0, t1 in zip(ends, ends[1:]):
        yr = datetime.fromtimestamp(t0, timezone.utc).year
        rows = []
        for u in univ:
            ten, tts = u["ten"]
            lp = perf.last_point(ten, tts, t0)
            if not lp or lp[0] < t0 - 10 * DAY:  # no quote in the 10 days before the month end
                continue
            y = lp[1]
            infl = get("PCPIPCH", u["imf"], yr - 1)
            cpts = [(x, perf.last_point(h, ts, t0)) for x, h, ts in u["curve"]]
            crv = bondmath.Curve([(x, p[1]) for x, p in cpts if p and p[0] >= t0 - 10 * DAY])
            roll = y - crv.at(9) if crv.covers(9, 0.1) and len(crv.x) > 1 and crv.x[0] < 9 else 0.0
            mod, _ = bondmath.par_duration(y, 10)
            c = u["cash"](t0)
            past = [v for _, v in perf.window(ten, tts, t0 - 3 * 365 * DAY, t0)]
            prim, bal, rev = get("GGXONLB_G01_GDP_PT", u["imf"], yr - 1), get("GGXCNL_G01_GDP_PT", u["imf"], yr - 1), get("GGR_G01_GDP_PT", u["imf"], yr - 1)
            fwd = perf.index(perf.window(ten, tts, t0 - 10 * DAY, t1), t0, t1, 10, u["cash"], cash_gb)
            if not fwd or fwd[-1][0] < t1 - 10 * DAY:
                continue
            rows.append({"code": u["code"], "ret": fwd[-1][1] - 1, "in": {
                "realY": y - infl if infl is not None else None,
                "carry": (y + mod * roll - c) / mod * 100 if c is not None else None,
                "cheap": sum(v < y for v in past) / len(past) if len(past) > 600 else None,
                "debt": get("GGXWDG_NGDP", u["imf"], yr - 1),
                "intRev": (prim - bal) / rev * 100 if None not in (prim, bal, rev) and rev else None}})
        if len(rows) < (10 if not only else 8):
            continue
        ranks = {}
        for k in PARTS:
            vals = [r["in"][k] for r in rows]
            ranks[k] = pct_rank([None if v is None else (-v if k in LOWER_BETTER else v) for v in vals])
            comp_ic[k].append(spearman(vals if k not in LOWER_BETTER else [None if v is None else -v for v in vals], [r["ret"] for r in rows]))
        for i, r in enumerate(rows):
            w = sum(PARTS[k] for k in PARTS if ranks[k][i] is not None)
            r["score"] = sum(ranks[k][i] * PARTS[k] for k in PARTS if ranks[k][i] is not None) / w if w else None
        ranked = sorted((r for r in rows if r["score"] is not None), key=lambda r: -r["score"])
        n = max(1, round(len(ranked) / 5))
        avg = lambda rs: sum(r["ret"] for r in rs) / len(rs)
        rec = {"t": t0, "n": len(ranked), "all": avg(ranked)}
        for g, pick in (("top", ranked[:n]), ("bottom", ranked[-n:])):
            codes = {r["code"] for r in pick}
            swapped = 1.0 if held[g] is None else 1 - len(codes & held[g]) / len(codes)
            rec[g] = avg(pick) - swapped * 2 * COST
            rec[g + "Codes"] = sorted(codes)
            held[g] = codes
        gbr = next((r for r in rows if r["code"] == "GB"), None)
        rec["gilts"] = gbr["ret"] if gbr else None
        rec["spread"] = rec["top"] - rec["bottom"]
        months.append(rec)
    if len(months) < 12:
        return None
    return summarise(months, comp_ic)


def summarise(months, comp_ic):
    def block(ms):
        ex_top = [m["top"] - m["all"] for m in ms]
        ex_bot = [m["bottom"] - m["all"] for m in ms]
        return {"from": ms[0]["t"], "to": ms[-1]["t"] + 31 * DAY, "months": len(ms),
                "topEx": sum(ex_top) / len(ms) * 12, "botEx": sum(ex_bot) / len(ms) * 12,
                "tTop": tstat(ex_top), "tBot": tstat(ex_bot), "tSpread": tstat([m["spread"] for m in ms]),
                "hitTop": sum(x > 0 for x in ex_top) / len(ms), "hitBot": sum(x < 0 for x in ex_bot) / len(ms)}
    ann = lambda xs: math.prod(1 + x for x in xs) ** (12 / len(xs)) - 1 if xs else None
    curves = {"t": [], "top": [], "bottom": [], "all": [], "gilts": []}
    lv = {k: 1.0 for k in ("top", "bottom", "all", "gilts")}
    for m in months:
        curves["t"].append(m["t"] + DAY)
        for k in lv:
            lv[k] *= 1 + (m[k] or 0)
            curves[k].append(round(lv[k], 5))
    half = len(months) // 2
    out = block(months)
    out.update({
        "topAnn": ann([m["top"] for m in months]), "botAnn": ann([m["bottom"] for m in months]),
        "allAnn": ann([m["all"] for m in months]), "giltsAnn": ann([m["gilts"] for m in months if m["gilts"] is not None]),
        "avgMarkets": round(sum(m["n"] for m in months) / len(months), 1), "cost": COST,
        "halves": [block(months[:half]), block(months[half:])],
        "components": {k: {"ic": (sum(x for x in v if x is not None) / max(1, sum(x is not None for x in v))) if v else None,
                           "t": tstat(v)} for k, v in comp_ic.items()},
        "curves": curves,
        "recent": [{"t": m["t"], "top": m["topCodes"], "bottom": m["bottomCodes"], "topRet": m["top"], "botRet": m["bottom"],
                    "allRet": m["all"]} for m in months[-6:]],
    })
    return out
