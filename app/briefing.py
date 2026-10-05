"""Weekly bond briefing: gather the week's facts and write a factual draft.

Run by .github/workflows/briefing.yml every Saturday morning. It saves
  data/briefings/facts/<date>.json  - every number the briefing may use
  data/briefings/<date>.md          - a plain factual draft (published straight away)
  data/briefings/index.json         - the archive list the site reads
A weekly scheduled Claude task on Max's PC then rewrites the draft into a proper briefing
using only those facts (see BRIEFING_PROMPT.md). If that doesn't run, the draft stays up.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bonds
import calendar_events

HERE = Path(__file__).parent
OUT = HERE.parent / "data" / "briefings"
HEADLINE = ["US", "GB", "DE", "FR", "IT", "JP"]


def long_date(iso, weekday=True):
    d = datetime.fromisoformat(iso)
    return f"{d.strftime('%A') + ' ' if weekday else ''}{d.day} {d.strftime('%B %Y')}"


def week_ending(now):
    """The last trading day the week's numbers run to: Friday at a weekend, otherwise today."""
    return (now - timedelta(days=now.weekday() - 4)).date() if now.weekday() >= 5 else now.date()


def bpw(v):
    if v is None:
        return "n/a"
    n = int(abs(v) + 0.5)
    return "unchanged" if n == 0 else f"{'up' if v > 0 else 'down'} {n} basis point{'s' if n != 1 else ''}"


def gather():
    d = bonds.build()
    now = datetime.now(timezone.utc)
    rows = {r["code"]: r for r in d["rows"]}
    bench = lambda r: next(b for b in r["bonds"] if b["tenor"] == r["bench"])

    def mkt(r):
        b = bench(r)
        return {"name": r["name"], "code": r["code"], "maturity": b["tenor"], "yield": b["y"],
                "weekChangeBp": b.get("d1w"), "monthChangeBp": b.get("d1m"), "yearChangeBp": b.get("d1y"),
                "realYield": b.get("realY"), "yieldHedgedIntoPounds": b.get("hedgedGbp"),
                "score": round(r["m"]["score"]) if r["m"]["score"] is not None else None, "signal": r["m"]["signal"],
                "scoreChangeWeek": r["m"].get("d1w"), "rating": (r["rating"] or {}).get("label"),
                "debtPctGdp": r["fiscal"]["debt"], "staleQuote": b.get("stale")}

    movers = sorted((mkt(r) for r in d["rows"] if bench(r).get("d1w") is not None and not bench(r).get("stale")),
                    key=lambda x: x["weekChangeBp"])
    scored = sorted((mkt(r) for r in d["rows"] if r["m"]["score"] is not None), key=lambda x: -x["score"])
    week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    credit = {c["id"]: c for c in d["credit"]}
    cr = lambda i: {"label": credit[i]["label"], "level": credit[i]["last"], "unit": "bp" if credit[i]["kind"] == "spread" else "%",
                    "weekChangeBp": credit[i]["d1w"], "monthChangeBp": credit[i]["d1m"],
                    "higherThanPctOfDaysSince": [credit[i]["pct"], datetime.fromtimestamp(credit[i]["since"], timezone.utc).year]} if i in credit else None
    banks, seen = [], set()
    for r in d["rows"]:
        p = r.get("policy")
        if not p or p["bank"] in seen:
            continue
        seen.add(p["bank"])
        last = p.get("last")
        if last and last["t"] >= (now - timedelta(days=8)).timestamp():
            banks.append({"bank": p["bank"], "country": "Euro area" if p["bank"] == "XM" else r["name"],
                          "from": last["from"], "to": last["to"],
                          "date": datetime.fromtimestamp(last["t"], timezone.utc).strftime("%Y-%m-%d")})
    p = d.get("paper")
    paper = None
    if p:
        last = {k: v[-1] if v else None for k, v in p["lines"].items()}
        paper = {"started": p["started"], "valuesGbp": last, "startValueGbp": 10000,
                 "topHoldings": [{"name": h["name"], "sincePick": h["since"]} for h in p["holdings"]],
                 "bottomHoldings": [{"name": h["name"], "sincePick": h["since"]} for h in p["bottomHoldings"]],
                 "nextPicks": p["nextRebalance"]}
    bt = d.get("backtest")
    us = rows.get("US")
    upcoming = [e for e in calendar_events.upcoming(days=9)]
    facts = {
        "weekEnding": week_ending(now).isoformat(), "generated": now.isoformat(timespec="minutes"),
        "headlineYields": [mkt(rows[c]) for c in HEADLINE if c in rows],
        "usCurve2s10sBp": us["slopes"].get("s2s10") if us else None,
        "usCurve2s10sWeekChangeBp": (us["slopes"]["s2s10"] - us["slopes"]["s2s10_1w"]) if us and us["slopes"].get("s2s10_1w") is not None and us["slopes"].get("s2s10") is not None else None,
        "franceMinusGermany10yBp": round((bench(rows["FR"])["y"] - bench(rows["DE"])["y"]) * 100) if "FR" in rows and "DE" in rows else None,
        "italyMinusGermany10yBp": round((bench(rows["IT"])["y"] - bench(rows["DE"])["y"]) * 100) if "IT" in rows and "DE" in rows else None,
        "biggestYieldRisesWeek": movers[::-1][:5], "biggestYieldFallsWeek": movers[:5],
        "invertedCurves": [r["name"] for r in d["rows"] if r.get("shape") == "Inverted"],
        "credit": [x for x in (cr("BAMLC0A0CM"), cr("BAMLH0A0HYM2"), cr("BAMLHE00EHYIOAS"), cr("BAMLEMCBPIOAS")) if x],
        "inflation": [x for x in (cr("T10YIE"), cr("T5YIFR"), cr("DFII10")) if x],
        "bondVolatilityMOVE": {"level": round(d["move"]["last"]), "monthChange": round(d["move"]["d1m"])} if d.get("move") else None,
        "centralBankMovesThisWeek": banks,
        "conditions": [{"rule": x["name"], "active": x["active"], "note": x["note"]} for x in d["rules"]],
        "highestScores": scored[:5], "lowestScores": scored[-5:][::-1],
        "biggestScoreRises": sorted((x for x in scored if x["scoreChangeWeek"] is not None), key=lambda x: -x["scoreChangeWeek"])[:5],
        "biggestScoreFalls": sorted((x for x in scored if x["scoreChangeWeek"] is not None), key=lambda x: x["scoreChangeWeek"])[:5],
        "signalChangesThisWeek": [{"name": rows[c["key"]]["name"] if c["key"] in rows else c["key"], "from": c["from"], "to": c["to"], "date": c["date"]}
                                  for c in (d.get("changes") or {}).get("changes", []) if c["date"] >= week_ago],
        "practicePortfolios": paper,
        "scoreTestOnThePast": {"months": bt["months"], "topVsAveragePerYear": bt["topEx"], "bottomVsAveragePerYear": bt["botEx"],
                               "reliabilityT": bt["tSpread"],
                               "developedOnlyTopVsAveragePerYear": (bt.get("dm") or {}).get("topEx")} if bt else None,
        "nextWeek": upcoming,
    }
    return facts


def draft(f):
    """A plain, factual Markdown draft built only from the facts."""
    L = [f"# Bond briefing: week to {long_date(f['weekEnding'])}", "",
         "*Automatic factual draft. Claude rewrites this into a fuller briefing each Saturday morning.*", "",
         "## Government bond yields", ""]
    for x in f["headlineYields"]:
        L.append(f"- {x['name']} {x['maturity']}: {x['yield']:.2f}%, {bpw(x['weekChangeBp'])} on the week ({bpw(x['monthChangeBp'])} over a month).")
    if f["usCurve2s10sBp"] is not None:
        L.append(f"- US 10-year minus 2-year: {round(f['usCurve2s10sBp'])} basis points.")
    if f["italyMinusGermany10yBp"] is not None:
        L.append(f"- Italy pays {f['italyMinusGermany10yBp']} basis points more than Germany for 10 years; France {f['franceMinusGermany10yBp']}.")
    L += ["", "## Biggest moves", ""]
    L.append("- Yields rose most in: " + ", ".join(f"{x['name']} ({bpw(x['weekChangeBp'])})" for x in f["biggestYieldRisesWeek"]) + ".")
    L.append("- Yields fell most in: " + ", ".join(f"{x['name']} ({bpw(x['weekChangeBp'])})" for x in f["biggestYieldFallsWeek"]) + ".")
    L += ["", "## Credit, inflation and volatility", ""]
    for c in f["credit"] + f["inflation"]:
        L.append(f"- {c['label']}: {c['level']:.0f}bp" if c["unit"] == "bp" else f"- {c['label']}: {c['level']:.2f}%")
        L[-1] += f", {bpw(c['weekChangeBp'])} on the week."
    if f["bondVolatilityMOVE"]:
        L.append(f"- Bond volatility (MOVE index): {f['bondVolatilityMOVE']['level']}.")
    if f["centralBankMovesThisWeek"]:
        L += ["", "## Central banks", ""]
        for b in f["centralBankMovesThisWeek"]:
            L.append(f"- {b['country']}: {b['from']}% to {b['to']}% on {b['date']}.")
    L += ["", "## Scores", ""]
    L.append("- Highest: " + ", ".join(f"{x['name']} {x['score']}" for x in f["highestScores"]) + ".")
    L.append("- Lowest: " + ", ".join(f"{x['name']} {x['score']}" for x in f["lowestScores"]) + ".")
    if f["signalChangesThisWeek"]:
        L.append("- Signal changes: " + "; ".join(f"{c['name']} {c['from']} to {c['to']}" for c in f["signalChangesThisWeek"]) + ".")
    p = f["practicePortfolios"]
    if p:
        v = p["valuesGbp"]
        L += ["", "## Practice portfolios", "",
              f"- Since {p['started']}, £10,000 in the top-scored 20% is worth £{v['top']:,.0f}; the lowest-scored 20% £{v['bottom']:,.0f}; "
              f"all markets £{v['all']:,.0f}; UK gilts £{v['gilts']:,.0f}; cash £{v['cash']:,.0f}."]
    if f["nextWeek"]:
        L += ["", "## Next week", ""] + [f"- {e['date']}: {e['who']} {e['what']}" for e in f["nextWeek"]]
    L += ["", "*For research and education only; not investment advice.*", ""]
    return "\n".join(L)


def main():
    facts = gather()
    date = facts["weekEnding"]
    (OUT / "facts").mkdir(parents=True, exist_ok=True)
    (OUT / "facts" / f"{date}.json").write_text(json.dumps(facts, indent=1, ensure_ascii=False), encoding="utf-8")
    md = OUT / f"{date}.md"
    by_claude = md.exists() and "author: Claude" in md.read_text(encoding="utf-8")[:300]
    if not by_claude:
        md.write_text(draft(facts), encoding="utf-8")
    index_path = OUT / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else []
    index = [e for e in index if e["date"] != date]
    index.insert(0, {"date": date, "title": f"Week to {long_date(date)}", "file": f"{date}.md",
                     "author": "Claude" if by_claude else "draft"})
    index_path.write_text(json.dumps(sorted(index, key=lambda e: e["date"], reverse=True), indent=1), encoding="utf-8")
    print(f"Briefing facts and {'existing Claude briefing kept' if by_claude else 'draft written'} for week to {date}.")


if __name__ == "__main__":
    main()
