"""UK gilt finder: every gilt in issue, its price, yield and after-tax yield, from the Debt Management Office.

Run once a day by .github/workflows/gilts.yml (never on the 15-minute loop: the DMO's site has a bot shield,
so it gets one polite request a day). It saves data/gilts.json, which build() reads.

Why after-tax yields matter: for a UK taxpayer, interest from a gilt is taxed as income but the gain as a
gilt is redeemed at 100 is free of capital gains tax. A low-coupon gilt bought well below 100 delivers most
of its return as tax-free gain, so after tax it can beat a higher-coupon gilt with the same gross yield.
"""
import csv
import io
import json
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from pathlib import Path

import bondmath

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "gilts.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; BondCompass/1.0; +https://github.com/maxgilbertson/bond-compass)"}
FRACTIONS = {"¼": .25, "½": .5, "¾": .75, "⅛": .125, "⅜": .375, "⅝": .625, "⅞": .875}
TAX_RATES = (0.20, 0.40, 0.45)


class Blocked(Exception):
    pass


def _get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        if "perfdrive" in r.geturl() or "validate." in r.geturl():
            raise Blocked("the DMO's bot shield asked for a CAPTCHA; not retrying")
        return r.read()


def coupon_of(name):
    """'4¼% Treasury Gilt 2034' or '4 1/4% Treasury Gilt 2034' or '0.875% ...' -> 4.25 / 0.875."""
    m = re.match(r"\s*(\d+(?:\.\d+)?)?\s*([¼½¾⅛⅜⅝⅞])?\s*(?:(\d+)/(\d+))?\s*%", name)
    if not m or not (m.group(1) or m.group(2) or m.group(3)):
        return None
    v = float(m.group(1) or 0) + FRACTIONS.get(m.group(2) or "", 0)
    if m.group(3):
        v += int(m.group(3)) / int(m.group(4))
    return v


def _date(s):
    for fmt in ("%d-%b-%Y", "%d %b %Y", "%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s.strip()[:19], fmt).date()
        except ValueError:
            continue
    return None


def _num(s):
    try:
        return float(str(s).replace(",", "").strip())
    except ValueError:
        return None


def parse(body):
    """Rows of {isin, name, clean, dirty, maturity} from a CSV or XML export, whatever the exact column names."""
    text = body.decode("utf-8-sig", "replace")
    records = []
    if text.lstrip().startswith("<"):
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            return []
        for el in root.iter():
            kids = {c.tag.split("}")[-1].lower(): (c.text or "").strip() for c in el}
            attrs = {k.lower(): v for k, v in el.attrib.items()}
            rec = {**attrs, **kids}
            if any("isin" in k for k in rec):
                records.append(rec)
    else:
        rows = list(csv.reader(io.StringIO(text)))
        head = next((i for i, r in enumerate(rows) if any("isin" in c.lower() for c in r)), None)
        if head is None:
            return []
        keys = [c.strip().lower() for c in rows[head]]
        records = [dict(zip(keys, r)) for r in rows[head + 1:] if len(r) >= len(keys) // 2]
    out = []
    pick = lambda rec, *words: next((v for k, v in rec.items() if all(w in k for w in words)), None)
    for rec in records:
        isin = pick(rec, "isin")
        name = pick(rec, "name") or pick(rec, "gilt") or pick(rec, "instrument")
        clean = _num(pick(rec, "clean") or "")
        if not (isin and name and clean):
            continue
        mat = _date(pick(rec, "redemption") or pick(rec, "maturity") or "")
        if mat is None:
            m = re.search(r"(20\d\d|19\d\d)\b", name)
            mat = date(int(m.group(1)), 6, 30) if m else None
        out.append({"isin": isin.strip(), "name": " ".join(name.split()), "clean": clean,
                    "dirty": _num(pick(rec, "dirty") or ""), "mat": mat})
    return out


def fetch(max_back=5):
    """The latest available day's prices (today, else up to max_back business days before)."""
    day = date.today()
    tried = 0
    while tried <= max_back:
        if day.weekday() < 5:
            for fmt in ("csv", "xml"):
                url = ("https://www.dmo.gov.uk/umbraco/surface/DataExport/GetDataExport?reportCode=D10B"
                       f"&exportFormatValue={fmt}&parameters=%26Trade%20Date%3D{day:%d}%2F{day:%m}%2F{day:%Y}")
                body = _get(url)
                rows = parse(body)
                print(f"{day} {fmt}: {len(body)} bytes, {len(rows)} gilts", flush=True)
                if len(rows) >= 20:
                    return day, fmt, rows
                if not rows:
                    print("  first bytes:", body[:300], flush=True)
                time.sleep(3)  # polite: one request every few seconds at most
            tried += 1
        day -= timedelta(days=1)
    raise SystemExit("no gilt prices found in the last business days")


def solve_yield(target_dirty, coupon, mat, settle):
    """Yield (%) at which the bond's dirty price equals target_dirty (bisection)."""
    lo, hi = -2.0, 25.0
    for _ in range(80):
        mid = (lo + hi) / 2
        a = bondmath.analytics(mid, coupon, mat, 2, settle)
        if a is None:
            return None
        if a["dirty"] > target_dirty:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def analyse(rows, day):
    gilts = []
    for r in rows:
        linker = "index" in r["name"].lower()
        c = coupon_of(r["name"])
        rec = {"isin": r["isin"], "name": r["name"], "linker": linker, "coupon": c,
               "mat": r["mat"].isoformat() if r["mat"] else None, "clean": r["clean"], "dirty": r["dirty"]}
        if not linker and c is not None and r["mat"] and r["mat"] > day:
            a0 = bondmath.analytics(5.0, c, r["mat"], 2, day)
            accrued = a0["accrued"] if a0 else 0.0
            dirty = r["dirty"] if r["dirty"] else r["clean"] + accrued
            y = solve_yield(dirty, c, r["mat"], day)
            if y is not None:
                a = bondmath.analytics(y, c, r["mat"], 2, day)
                rec.update({"dirty": round(dirty, 4), "ytm": round(y, 4), "mod": round(a["mod"], 2), "yrs": round(a["yrs"], 2),
                            "dv01": round(a["dv01"])})
                # after tax: coupons taxed at the rate, the pull to 100 tax-free (gilts are exempt from CGT)
                for t in TAX_RATES:
                    at = solve_yield(dirty, c * (1 - t), r["mat"], day)
                    rec[f"at{round(t * 100)}"] = round(at, 4) if at is not None else None
        gilts.append(rec)
    return sorted(gilts, key=lambda g: g["mat"] or "9999")


def main():
    try:
        day, fmt, rows = fetch()
    except Blocked as e:
        raise SystemExit(str(e))
    gilts = analyse(rows, day)
    OUT.write_text(json.dumps({"date": day.isoformat(), "fetched": int(time.time()), "format": fmt,
                               "source": "UK Debt Management Office, report D10B (prices for the Gilt Purchase and Sale Service)",
                               "gilts": gilts}, indent=1, ensure_ascii=False), encoding="utf-8")
    conv = [g for g in gilts if g.get("ytm") is not None]
    print(f"saved {len(gilts)} gilts ({len(conv)} conventional with yields) for {day}")


if __name__ == "__main__":
    main()
