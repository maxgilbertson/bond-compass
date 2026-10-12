"""How safe is each government? Warning lights on the things that have tipped governments into trouble before.

Each measure gets a light from fixed thresholds that are shown on the page: "low" (green), "some" (amber) or "high"
(red) risk. Where the IMF publishes a benchmark (its debt sustainability framework for countries that borrow in
markets, 2013, still the usual reference), the light uses it; the other thresholds are Bond Compass's own and say so.
Measures group into five pillars, and a pillar's light is the average of its measures' lights.

None of this feeds the score (bonds.WEIGHTS): it sits beside it, for judging how safe the government behind a
bond is.
"""

LIGHT_POINTS = {"low": 0, "some": 1, "high": 2}

PILLARS = [
    ("debt", "Debt", "How much the government owes, and which way it's heading"),
    ("bill", "Interest bill", "How much of its income goes on interest, and how much more a rise in rates would cost"),
    ("refi", "Refinancing", "How quickly higher rates feed through: how much debt has to be replaced soon"),
    ("lenders", "Lenders", "Who it borrows from, and in which currency: lenders abroad can leave fast"),
    ("record", "Track record", "Defaults, inflation, institutions and credit rating"),
]

# key: pillar, label, unit, thresholds (amber from, red from) for developed and emerging markets, whether a higher
# value is worse, where the thresholds come from, and what the measure means
MEASURES = {
    "debt": dict(pillar="debt", label="Government debt", unit="% of GDP", dm=(60, 85), em=(50, 70), worse="higher", by="imf",
                 about="Gross general-government debt as a share of the economy (IMF). The IMF treats more than 85% of GDP "
                       "(advanced economies) or 70% (emerging) as a high-risk level."),
    "debtChg": dict(pillar="debt", label="Debt over the next 5 years", unit="points of GDP", dm=(3, 8), em=(3, 8), worse="higher", by="own",
                    about="How far the IMF expects debt to rise (+) or fall (−) as a share of GDP over the next five years."),
    "gap": dict(pillar="debt", label="Budget gap", unit="% of GDP", dm=(0.5, 1.5), em=(0.5, 1.5), worse="higher", by="own",
                about="How far this year's budget (before interest) falls short of what would hold debt steady at today's "
                      "10-year yield and the IMF's growth forecast. Positive = debt on course to keep rising."),
    "intRev": dict(pillar="bill", label="Interest bill", unit="% of revenue", dm=(8, 15), em=(8, 15), worse="higher", by="own",
                   about="Net interest paid as a share of all government revenue this year (IMF). Over 15% leaves little room "
                         "for anything else and is a common warning level."),
    "intRev5": dict(pillar="bill", label="Interest bill in 5 years", unit="% of revenue", dm=(8, 15), em=(8, 15), worse="higher", by="own",
                    about="The same share five years from now, from the IMF's forecasts of the budget."),
    "perPoint": dict(pillar="bill", label="Cost of a 1-point rise in rates", unit="% of revenue", dm=(3, 5), em=(3, 5), worse="higher", by="own",
                     about="How much more of its revenue the government would spend on interest if all interest rates rose by "
                           "1 percentage point and stayed there, once all its debt had been refinanced at the higher rate "
                           "(debt divided by revenue). The bigger the debt compared with the tax take, the bigger the hit."),
    "atm": dict(pillar="refi", label="Average time to maturity", unit="years", dm=(7, 4), em=(7, 4), worse="lower", by="own",
                about="How long, on average, until the government's debt has to be repaid and refinanced. The shorter it is, "
                      "the faster higher interest rates feed into the interest bill."),
    "due1y": dict(pillar="refi", label="Due within a year", unit="% of its bonds", dm=(20, 30), em=(15, 25), worse="higher", by="own",
                  about="The share of its bonds and bills that mature within 12 months and must be refinanced at "
                        "whatever rate the market then demands. Where only bills are counted it is a minimum."),
    "gfn": dict(pillar="refi", label="Financing need this year", unit="% of GDP", dm=(15, 20), em=(10, 15), worse="higher", by="imf",
                about="This year's deficit plus the debt falling due: what the government must borrow from the market "
                      "(IMF Fiscal Monitor; an estimate where the IMF gives none). The IMF treats more than 20% of GDP "
                      "(advanced economies) or 15% (emerging) as a high-risk level."),
    "floating": dict(pillar="refi", label="Floating or inflation-linked", unit="% of its bonds", dm=(15, 30), em=(15, 30), worse="higher", by="own",
                     about="The share of its bonds whose interest follows short-term rates or inflation, so the bill "
                           "rises at once when they do, without waiting for the bond to mature."),
    "fx": dict(pillar="lenders", label="In foreign currency", unit="% of its bonds", dm=(20, 60), em=(20, 60), worse="higher", by="imf",
               about="The share of its bonds owed in other countries' currencies. They can't be inflated away or repaid "
                     "by printing money, and a falling currency makes them bigger. The IMF's thresholds: 20% and 60%."),
    "abroad": dict(pillar="lenders", label="Held abroad", unit="% of debt", dm=None, em=(15, 45), worse="higher", by="imf",
                   about="The share of government debt held by investors outside the country. In emerging markets foreign "
                         "lenders can sell up and leave quickly in a crisis (the IMF's thresholds: 15% and 45%). Not scored "
                         "for advanced economies, whose bonds are widely held abroad as safe assets and reserves."),
    "reserves": dict(pillar="lenders", label="Foreign-exchange reserves", unit="months of imports", dm=None, em=(6, 3), worse="lower", by="own",
                     about="How many months of imports the central bank's reserves could pay for. Matters most for emerging "
                           "markets; three months is the traditional minimum. Not scored for developed markets."),
    "defaults": dict(pillar="record", label="Default record", unit="", dm=None, em=None, worse="special", by="own",
                     about="Years since 1960 in which the government was in default on its bonds, bank loans or local-currency "
                           "debt (US$100m or more), from the Bank of Canada and Bank of England sovereign default database. "
                           "Arrears to other governments and official lenders aren't counted."),
    "inflation": dict(pillar="record", label="Inflation, last 10 years", unit="% a year", dm=(3, 6), em=(3, 6), worse="higher", by="own",
                      about="Average consumer-price inflation over the last ten years (IMF). High inflation erodes what bonds pay "
                            "and is often a sign of weak policy."),
    "governance": dict(pillar="record", label="Governance", unit="out of 100", dm=(75, 50), em=(75, 50), worse="lower", by="own",
                       about="The World Bank's Worldwide Governance Indicators: the average of six percentile ranks among about "
                             "200 countries (government effectiveness, rule of law, control of corruption, regulatory quality, "
                             "political stability, voice and accountability). 100 = best in the world."),
    "rating": dict(pillar="record", label="Credit rating", unit="", dm=(14.5, 11.5), em=(14.5, 11.5), worse="lower", by="own",
                   about="The average of S&P, Moody's and Fitch. Low risk = A− or better; some = BBB range; high = below "
                         "investment grade (BB+ or lower)."),
}


def light(key, v, dm):
    """'low', 'some' or 'high' risk for one measure's value, or None if there's no value or no threshold."""
    m = MEASURES[key]
    th = m["dm"] if dm else m["em"]
    if v is None or th is None:
        return None
    amber, red = th
    if m["worse"] == "higher":
        return "high" if v >= red else "some" if v >= amber else "low"
    return "high" if v < red else "some" if v < amber else "low"


def default_light(rec):
    if not rec or rec.get("years") is None:
        return None
    last = rec.get("last")
    return "low" if not last else "high" if last >= 2000 else "some"


def pillar_light(lights):
    pts = [LIGHT_POINTS[x] for x in lights if x]
    if not pts:
        return None
    avg, reds = sum(pts) / len(pts), pts.count(2)
    # one red measure is enough to make its group amber; two (or an average of 1.5) make it red
    return "high" if avg >= 1.5 or reds >= 2 else "some" if avg >= 0.5 or reds else "low"


def verdict(pillars):
    """A plain verdict from the five groups' lights: red counts 2 points, amber 1 (out of 10; scaled up if a group
    has no data). Needs at least three groups."""
    pts = [LIGHT_POINTS[p] for p in pillars.values() if p]
    if len(pts) < 3:
        return None
    total, reds = sum(pts) * len(pillars) / len(pts), pts.count(2)
    if total >= 7 or (reds >= 2 and total >= 6):
        return "High risk"
    if total >= 5 or reds >= 2 or (reds and total >= 4):
        return "Several warning signs"
    if total >= 2 or reds:
        return "Some warning signs"
    return "Few warning signs"


def assess(values, dm, overrides=None):
    """values: {measure key: number (or the default record)} -> lights, pillar lights and a verdict.
    overrides: lights set by a rule rather than a threshold (a government that is a net creditor)."""
    lights = {k: (default_light(v) if k == "defaults" else light(k, v, dm)) for k, v in values.items() if k in MEASURES}
    lights.update(overrides or {})
    pillars = {p: pillar_light([lights.get(k) for k, m in MEASURES.items() if m["pillar"] == p]) for p, _, _ in PILLARS}
    return {"lights": lights, "pillars": pillars, "verdict": verdict(pillars)}


def _avg(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def block(r, ext, gbp_per_usd):
    """Everything the page shows about the safety of one government, from the row's IMF numbers and the extra
    sources (ext: per-source dicts keyed by the market's two-letter code)."""
    f, code = r["fiscal"], r["code"]
    dm = code in IMF_ADVANCED  # the IMF sets its benchmarks separately for advanced and emerging economies
    year = f["year"]
    by_year = {y: (g, rv) for y, g, rv in f.get("intPath") or []}
    infl = {y: v for y, v in f.get("inflHist") or []}
    past = [infl[y] for y in range(year - 10, year) if y in infl]
    worst = max(((infl[y], y) for y in range(year - 10, year) if y in infl), default=(None, None))
    usd = lambda pct_gdp: pct_gdp / 100 * f["gdpUsd"] if pct_gdp is not None and f.get("gdpUsd") else None
    gbp = lambda v: round(v * gbp_per_usd) if v is not None and gbp_per_usd else None

    prof = (ext.get("profile") or {}).get(code) or {}  # how the debt is structured: safety_sources.profile()
    gov = (ext.get("wgi") or {}).get(code) or {}
    res = (ext.get("reserves") or {}).get(code) or {}
    rec = (ext.get("defaults") or {}).get(code)
    # a government whose financial assets exceed its debt (IMF net debt below zero, or a known case the IMF has no
    # net figure for) isn't at risk from its gross debt or from refinancing it: its assets pay interest too
    creditor = NET_CREDITOR.get(code) or (
        f"Its financial assets exceed its debt (IMF net debt {f['netDebt']:.0f}% of GDP)." if (f.get("netDebt") or 0) < 0 else None)

    due1y, floating = prof.get("due1y"), prof.get("floating")
    gfn, gfn_est = prof.get("gfn"), False
    if gfn is None and due1y is not None and f.get("debt") is not None and f.get("balance") is not None:
        gfn, gfn_est = round(max(0.0, -f["balance"]) + f["debt"] * due1y / 100, 1), True  # deficit plus debt falling due
    gov_ranks = [gov.get(k) for k in ("ge", "rl", "cc", "rq", "pv", "va")]
    values = {
        "debt": f.get("debt"),
        "debtChg": round(f["debtIn5y"] - f["debt"], 1) if f.get("debtIn5y") is not None and f.get("debt") is not None else None,
        "gap": f.get("gap"),
        "intRev": f.get("intRev"),
        "intRev5": (by_year.get(year + 5) or (None, None))[1],
        "perPoint": round(f["debt"] / f["revenue"], 2) if f.get("debt") is not None and f.get("revenue") else None,
        "atm": prof.get("atm"),
        "due1y": due1y,
        "gfn": gfn,
        "floating": floating,
        "fx": prof.get("fx"),
        "abroad": prof.get("abroad"),
        "reserves": res.get("months"),
        "defaults": rec,
        "inflation": round(_avg(past), 2) if past else None,
        "governance": round(_avg(gov_ranks), 1) if any(x is not None for x in gov_ranks) else None,
        "rating": (r.get("rating") or {}).get("avg"),
    }
    out = assess(values, dm, {k: "low" for k in ("debt", "debtChg", "perPoint", "atm", "due1y", "gfn", "floating")
                              if values[k] is not None} if creditor else None)
    interest_usd = usd(f.get("interest"))
    out.update({
        "values": values,
        "money": {"interestUsd": round(interest_usd) if interest_usd is not None else None, "interestGbp": gbp(interest_usd),
                  "debtUsd": round(usd(f.get("debt"))) if usd(f.get("debt")) is not None else None, "debtGbp": gbp(usd(f.get("debt")))},
        "inflWorst": {"v": worst[0], "year": worst[1]} if worst[0] is not None else None,
        "profile": prof or None, "gfnEstimate": gfn_est, "governance": gov or None,
        "reserves": res or None, "regime": REGIME.get(code), "creditor": creditor, "adv": dm,
    })
    return out


# The IMF's "advanced economies" among the markets followed; every other market counts as emerging
IMF_ADVANCED = {"US", "CA", "GB", "DE", "FR", "IT", "ES", "NL", "BE", "AT", "PT", "GR", "IE", "FI", "CH", "SE", "NO",
                "JP", "AU", "NZ", "HK", "SG", "KR", "IL", "CZ", "DK", "TW"}

# Governments with more financial assets than debt that the IMF publishes no net-debt figure for
NET_CREDITOR = {
    "SG": "Singapore's government has more assets than debt: by law it can't spend what it raises from its main "
          "bonds (they give the CPF pension fund a safe asset and build a bond market); the money is invested.",
}

# How each currency is managed (IMF de facto classification, simplified); euro members can't print their own money
REGIME = {}


def meta():
    """Labels, thresholds and explanations for the page, so the rules are shown exactly as applied."""
    return {"pillars": [{"key": k, "label": l, "about": a} for k, l, a in PILLARS],
            "measures": {k: {x: m[x] for x in ("pillar", "label", "unit", "dm", "em", "worse", "by", "about")} for k, m in MEASURES.items()}}
