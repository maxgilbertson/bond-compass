"""Daily alerts: notable changes since the previous trading day's record, written as a short Markdown note.

The daily GitHub job (daily.yml) runs this after saving the day's record. If anything crossed a line, it
opens an issue in the repository titled "Bond Compass alerts <date>"; GitHub notifies the repository owner
(by email and in the GitHub app, depending on their notification settings). Nothing is sent anywhere else.

What counts (thresholds below, deliberately few so alerts stay worth reading):
  - a market's signal changed (e.g. Neutral -> Overweight)
  - a benchmark yield moved 20bp or more in a day (15bp for developed markets)
  - a yield curve inverted or stopped being inverted (10-year minus 2-year crossed zero)
  - a euro-area spread over Germany moved 10bp or more in a day
  - US high-yield or investment-grade spreads moved into the widest or tightest 10% of the last 3 years
  - a central bank changed its rate
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import markets
import tracking

BIG_MOVE_DM, BIG_MOVE_EM, SPREAD_MOVE = 15, 20, 10


def compare(data):
    """Alerts from today's build compared with the previous saved record. Returns a list of (heading, line)."""
    hist = tracking.load_history()
    today = tracking.today_key()
    prev = next((h for h in reversed(hist) if h["date"] < today), None)
    rows = {r["code"]: r for r in data["rows"]}
    out = []
    if prev:
        for code, r in rows.items():
            old = prev["rows"].get(code)
            if old and old[3] and r["m"]["signal"] and old[3] != r["m"]["signal"]:
                out.append(("Signal changes", f"**{r['name']}**: {old[3]} → {r['m']['signal']} (score {old[0]:.0f} → {r['m']['score']:.0f})"))
            b = next(x for x in r["bonds"] if x["tenor"] == r["bench"])
            if old and old[4] == r["bench"] and old[5] is not None:
                move = (b["y"] - old[5]) * 100
                if abs(move) >= (BIG_MOVE_DM if r["dm"] else BIG_MOVE_EM):
                    out.append(("Big yield moves", f"**{r['name']}** {r['bench']}: {old[5]:.2f}% → {b['y']:.2f}% ({move:+.0f}bp; {'prices down' if move > 0 else 'prices up'})"))
        # euro-area spreads over Germany
        de_old, de = prev["rows"].get("DE"), rows.get("DE")
        if de_old and de:
            de_now = next(x for x in de["bonds"] if x["tenor"] == de["bench"])["y"]
            for code in sorted(markets.EURO - {"DE"}):
                o, r = prev["rows"].get(code), rows.get(code)
                if not (o and r and o[4] == r["bench"] == "10Y" and de_old[4] == "10Y"):
                    continue
                y = next(x for x in r["bonds"] if x["tenor"] == "10Y")["y"]
                was, now_ = (o[5] - de_old[5]) * 100, (y - de_now) * 100
                if abs(now_ - was) >= SPREAD_MOVE:
                    out.append(("Euro-area spreads", f"**{r['name']}** over Germany (10-year): {was:.0f}bp → {now_:.0f}bp ({now_ - was:+.0f}bp)"))
    # curve inversions, from the yield record (yesterday's close vs today)
    rec = _yield_record()
    if len(rec) >= 2:
        (d0, y0), (d1, y1) = rec[-2], rec[-1]
        for m in markets.MARKETS:
            code = m[0]
            s2, s10 = markets.symbol(code, "2Y"), markets.symbol(code, "10Y")
            if all(k in y0 and k in y1 for k in (s2, s10)):
                a, b = y0[s10] - y0[s2], y1[s10] - y1[s2]
                if a >= 0 > b:
                    out.append(("Yield curves", f"**{m[1]}**'s curve has inverted: the 2-year yield is now {abs(b) * 100:.0f}bp above the 10-year"))
                elif a < 0 <= b:
                    out.append(("Yield curves", f"**{m[1]}**'s curve is no longer inverted (10-year minus 2-year: {b * 100:+.0f}bp)"))
    for c in data.get("credit", []):
        if c["id"] in ("BAMLH0A0HYM2", "BAMLC0A0CM") and (c["pct"] >= 90 or c["pct"] <= 10):
            out.append(("Credit", f"**{c['label']}** spread {c['last']:.0f}bp: {'wider' if c['pct'] >= 90 else 'tighter'} than {c['pct'] if c['pct'] >= 90 else 100 - c['pct']}% of days in the last 3 years"))
    now = datetime.now(timezone.utc).timestamp()
    seen = set()
    for r in data["rows"]:
        p = r.get("policy")
        if p and p["bank"] not in seen and p.get("last") and p["last"]["t"] >= now - 3 * 86400:
            seen.add(p["bank"])
            l = p["last"]
            out.append(("Central banks", f"**{'Euro area (ECB)' if p['bank'] == 'XM' else r['name']}**: policy rate {l['from']}% → {l['to']}%"))
    return out


def _yield_record():
    f = sorted((Path(__file__).resolve().parent.parent / "data" / "history").glob("yields-*.json"))
    days = {}
    for p in f[-2:]:
        days.update(json.loads(p.read_text(encoding="utf-8")))
    return sorted(days.items())


def note(alerts, date):
    if not alerts:
        return None
    groups = {}
    for h, line in alerts:
        groups.setdefault(h, []).append(line)
    L = [f"Changes on {date} worth a look. Details: https://maxgilbertson.github.io/bond-compass/", ""]
    for h, lines in groups.items():
        L += [f"### {h}", ""] + [f"- {x}" for x in lines] + [""]
    L.append("_Automatic note from the daily record. Not investment advice._")
    return "\n".join(L)
