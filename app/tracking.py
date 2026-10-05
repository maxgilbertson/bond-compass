"""Keeping a real record: daily score snapshots, a log of signal changes, and practice portfolios.

The files live in the repository (data/history/scores-<year>.jsonl, data/paper/bonds.json) and are
written by the daily GitHub Action (snapshot.py), so the record builds up whether or not a PC is on.
A test on past data can be tuned until it looks good; this live record can't, because each month's
picks are saved before anyone knows how they'll do.
"""
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import perf

DATA = Path(__file__).resolve().parent.parent / "data"
HISTORY = DATA / "history"
PAPER = DATA / "paper" / "bonds.json"
START_VALUE = 10_000
COST_PER_TRADE = 0.0005  # assumed one-way cost: dealer spread on government bonds plus rolling the currency hedge
DAY = 86400


def today_key(ts=None):
    return datetime.fromtimestamp(ts or time.time(), timezone.utc).strftime("%Y-%m-%d")


def day_end(key):
    return datetime.strptime(key, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() + DAY - 1


def _read_lines(path):
    out = []
    for line in path.read_text(encoding="utf-8").splitlines() if path.exists() else []:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out

# ---------------------------------------------------------------- daily score snapshots

def write_snapshot(data, date=None):
    """One line per day in a yearly file: {date, rows: {code: [score, value, safety, signal, tenor, yield]}, rules}.
    Re-running a day replaces its line."""
    date = date or today_key()
    path = HISTORY / f"scores-{date[:4]}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = {}
    for r in data["rows"]:
        b = next(x for x in r["bonds"] if x["tenor"] == r["bench"])
        m = r["m"]
        rows[r["code"]] = [m["score"], m["value"], m["safety"], m["signal"], r["bench"], b["y"]]
    line = {"date": date, "rows": rows, "rules": [x["name"] for x in data["rules"] if x["active"]]}
    days = [d for d in _read_lines(path) if d.get("date") != date] + [line]
    path.write_text("".join(json.dumps(d, separators=(",", ":")) + "\n" for d in sorted(days, key=lambda d: d["date"])),
                    encoding="utf-8")
    return path


def load_history():
    days = [d for f in sorted(HISTORY.glob("scores-*.jsonl")) for d in _read_lines(f) if "date" in d]
    return sorted(days, key=lambda d: d["date"])


def score_changes(rows):
    """Each market's score a week and four weeks ago (from the saved snapshots), and its recorded path."""
    hist = load_history()
    out = {}
    if not hist:
        return out
    now = time.time()
    keyed = [(day_end(h["date"]), h) for h in hist]
    for r in rows:
        path = [[t, h["rows"][r["code"]][0]] for t, h in keyed if r["code"] in h["rows"] and h["rows"][r["code"]][0] is not None]
        if not path:
            continue
        ago = lambda d: perf.at_or_before(path, now - d * DAY)
        s = r["m"]["score"]
        out[r["code"]] = {"d1w": None if ago(7) is None or s is None else round(s - ago(7), 1),
                          "d1m": None if ago(28) is None or s is None else round(s - ago(28), 1),
                          "path": path[-90:]}
    return out


def signal_log(rows):
    """Every recorded change of signal, from the saved daily snapshots plus today's live signal."""
    seq = [(h["date"], {c: v[3] for c, v in h["rows"].items()}, False) for h in load_history()]
    live = {r["code"]: r["m"]["signal"] for r in rows}
    today = today_key()
    if seq and seq[-1][0] == today:
        seq[-1] = (today, live, True)
    else:
        seq.append((today, live, True))
    prev, changes = {}, []
    for date, sigs, is_live in seq:
        for c, sig in sigs.items():
            if sig and prev.get(c) and sig != prev[c]:
                changes.append({"date": date, "key": c, "from": prev[c], "to": sig, "live": is_live})
            if sig:
                prev[c] = sig
    return {"since": seq[0][0], "days": len(seq), "changes": changes[-300:]}

# ---------------------------------------------------------------- practice ("paper") portfolios

def load_paper():
    try:
        return json.loads(PAPER.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def maybe_rebalance(rows, now=None):
    """At the first snapshot of each month, save the new top and bottom 20% by score. Returns True if it did."""
    now = now or time.time()
    date = today_key(now)
    log = load_paper() or {
        "started": date, "startValue": START_VALUE, "costPerTrade": COST_PER_TRADE, "rebalances": [],
        "rule": "On the first weekday of each month, put equal amounts into the benchmark bonds of the 20% of markets "
                "with the highest scores, currency hedged back to pounds. Compare with the lowest-scored 20%, with all "
                "markets in equal amounts, with UK 10-year gilts and with cash at the Bank of England's rate."}
    if log["rebalances"] and log["rebalances"][-1]["date"][:7] == date[:7]:
        return False
    ranked = sorted((r for r in rows if r["m"].get("score") is not None), key=lambda r: -r["m"]["score"])
    k = max(1, round(len(ranked) / 5))
    log["rebalances"].append({"date": date, "ts": int(now),
                              "top": [r["code"] for r in ranked[:k]], "bottom": [r["code"] for r in ranked[-k:]],
                              "all": [r["code"] for r in ranked],
                              "scores": {r["code"]: r["m"]["score"] for r in ranked}})
    PAPER.parent.mkdir(parents=True, exist_ok=True)
    PAPER.write_text(json.dumps(log, indent=1), encoding="utf-8")
    return True


def paper_report(idx, gilt_idx, cash_idx, names):
    """Rebuild each practice portfolio's value in pounds from the saved monthly picks.

    idx[code] = that market's benchmark bond, hedged into pounds, as a daily [[t, value]] index;
    gilt_idx = UK 10-year gilts; cash_idx = cash earning Bank Rate. Every line starts at 10,000.
    At each monthly pick the portfolio is reset to equal amounts in the new holdings, paying the
    assumed trading cost on the share it had to swap.
    """
    log = load_paper()
    if not log or not log["rebalances"]:
        return None
    rebs, cost = log["rebalances"], log.get("costPerTrade", COST_PER_TRADE)
    first = day_end(rebs[0]["date"])
    days = [first + DAY * k for k in range(max(0, int((time.time() - first) // DAY)) + 1)]
    mean = lambda xs: sum(xs) / len(xs) if xs else 1.0
    val = lambda s, t: perf.at_or_before(s, t) if s else None

    def line(group):
        value, path, held_prev = float(START_VALUE), [], None
        for k, reb in enumerate(rebs):
            seg_start = day_end(reb["date"])
            seg_end = day_end(rebs[k + 1]["date"]) if k + 1 < len(rebs) else None
            if group == "gilts":
                legs = [gilt_idx]
            elif group == "cash":
                legs = [cash_idx]
            else:
                held = reb[group] if group in reb else reb["top"]
                legs = [idx.get(c) for c in held]
                if group in ("top", "bottom"):
                    hs = set(held)
                    swapped = 1.0 if held_prev is None else 1 - len(hs & held_prev) / len(hs)
                    value *= 1 - swapped * (1 if held_prev is None else 2) * cost
                    held_prev = hs
            base = [(leg, val(leg, seg_start)) for leg in legs]
            base = [(leg, b) for leg, b in base if b]
            for d in days:
                if d >= seg_start and (seg_end is None or d < seg_end):
                    path.append(round(value * mean([(val(leg, d) or b) / b for leg, b in base]), 2))
            if seg_end is not None:
                value *= mean([(val(leg, seg_end) or b) / b for leg, b in base])
        return path

    last = rebs[-1]
    seg_start = day_end(last["date"])

    def since(codes):
        out = []
        for c in codes:
            s = idx.get(c)
            b, n = val(s, seg_start), val(s, days[-1])
            out.append({"key": c, "name": names.get(c, c), "since": (n / b - 1) if (b and n) else None})
        return sorted(out, key=lambda x: -(x["since"] if x["since"] is not None else -9))

    d = datetime.fromtimestamp(days[-1], timezone.utc)
    return {
        "started": rebs[0]["date"], "costPerTrade": cost, "rule": log.get("rule"), "t": days,
        "lines": {g: line(g) for g in ("top", "bottom", "all", "gilts", "cash")},
        "rebalances": [{"date": r["date"], "top": r["top"], "bottom": r["bottom"]} for r in rebs],
        "holdings": since(last["top"]), "bottomHoldings": since(last["bottom"]),
        "nextRebalance": datetime(d.year + (d.month == 12), d.month % 12 + 1, 1, tzinfo=timezone.utc).strftime("%Y-%m-%d"),
    }
