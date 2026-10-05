"""The daily record: every bond yield (data/history/yields-<year>.json), every score (scores-<year>.jsonl)
and the monthly practice-portfolio picks (data/paper/bonds.json), all kept in the repository.

CNBC keeps no history for some maturities (the Reuters-style "live only" quotes, India's and Hong Kong's
10-year, New Zealand's bills...). Saving each day's closing yields ourselves builds that history from now on,
and is a backup if CNBC's history ever goes missing. GitHub Actions runs this every weekday after the US close
(.github/workflows/daily.yml); bonds.py merges the record in wherever CNBC has nothing.
"""
import json
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "data" / "history"


def load():
    """{symbol: [[day, yield], ...]} from every saved year, oldest first."""
    out = {}
    for f in sorted(DIR.glob("yields-*.json")):
        try:
            days = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        for day, ys in sorted(days.items()):
            t = int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
            for sym, y in ys.items():
                out.setdefault(sym, []).append([t, y])
    return out


def save():
    import markets
    import sources
    syms = [s for m in markets.MARKETS for _, s, _ in markets.points(m)]
    q = sources.quotes(syms)
    now = time.time()
    # only quotes that traded in the last 4 days count as today's close
    ys = {s: v["y"] for s, v in sorted(q.items()) if v.get("time") and now - v["time"] < 4 * 86400}
    if len(ys) < len(syms) * 0.5:
        raise SystemExit(f"only {len(ys)} of {len(syms)} quotes; not saving")
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    DIR.mkdir(parents=True, exist_ok=True)
    f = DIR / f"yields-{day[:4]}.json"
    days = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    days[day] = ys
    f.write_text(json.dumps(dict(sorted(days.items())), separators=(",", ":")).replace('},"', '},\n"'), encoding="utf-8")
    print(f"saved {len(ys)} yields for {day}")


def main():
    """The daily job: save today's yields, then every score, and make the monthly practice-portfolio picks."""
    import alerts
    import bonds
    import tracking
    save()
    data = bonds.build()
    if len(data["rows"]) < 25:
        raise SystemExit(f"only {len(data['rows'])} markets loaded; not saving scores")
    text = alerts.note(alerts.compare(data), tracking.today_key())
    if text:  # the daily job posts this as a GitHub issue, then deletes it
        (ROOT / "alerts-today.md").write_text(text, encoding="utf-8")
        print(text)
    tracking.write_snapshot(data)
    if tracking.maybe_rebalance(data["rows"]):
        print("new monthly picks:", ", ".join(tracking.load_paper()["rebalances"][-1]["top"]))
    print(f"saved scores for {tracking.today_key()}: {len(data['rows'])} markets")


if __name__ == "__main__":
    main()
