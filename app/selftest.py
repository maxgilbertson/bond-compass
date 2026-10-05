"""Checks run before every publish: the bond maths against textbook values, and the return and curve helpers.

python app/selftest.py exits with an error if anything is off, which stops the GitHub job, so the last good
version of the site stays online instead of one with broken numbers.
"""
import math
import sys
from datetime import date

import bondmath
import perf

FAILS = []


def check(name, got, want, tol):
    ok = got is not None and abs(got - want) <= tol
    print(f"{'ok  ' if ok else 'FAIL'} {name}: {got} (expected {want} +/- {tol})")
    if not ok:
        FAILS.append(name)


today = date(2026, 1, 15)
# a 10-year 5% semi-annual bond on a coupon date, yielding 5%, is priced at par
a = bondmath.analytics(5.0, 5.0, date(2036, 1, 15), 2, today)
check("par bond clean price", a["clean"], 100.0, 0.01)
check("par bond modified duration", a["mod"], 7.7946, 0.01)
check("par bond Macaulay duration", a["mac"], 7.9894, 0.01)
check("par bond DV01 per 1m", a["dv01"], 779.5, 1.5)
# accrued interest halfway through a coupon period: half a coupon
a = bondmath.analytics(5.0, 5.0, date(2036, 4, 15), 2, today)
check("accrued interest, mid-period", a["accrued"], 1.25, 0.03)
# a 5-year zero-coupon bond at 4%
z = bondmath.analytics(4.0, None, date(2031, 1, 15), 2, today)
check("zero-coupon price", z["dirty"], 100 / 1.04 ** 5, 0.05)
# a rise in yield lowers the price; duration x 1bp is about the DV01
lo, hi = bondmath.analytics(5.0, 5.0, date(2036, 1, 15), 2, today), bondmath.analytics(5.01, 5.0, date(2036, 1, 15), 2, today)
check("price change for +1bp vs DV01", (lo["dirty"] - hi["dirty"]) / 100 * 1e6, lo["dv01"], 2)
# curve interpolation and flat ends
c = bondmath.Curve([(2, 4.0), (10, 5.0)])
check("curve midpoint", c.at(6), 4.5, 1e-9)
check("curve flat beyond the end", c.at(30), 5.0, 1e-9)
# Nelson-Siegel recovers a known curve
truth = {"b": [5.0, -1.5, 1.0], "lam": 2.2}
pts = [(t, bondmath.curve_at(truth, t)) for t in (0.5, 1, 2, 3, 5, 7, 10, 20, 30)]
fit = bondmath.fit_curve(pts)
check("fitted curve error", fit["rmse"], 0.0, 0.01)
check("forward 5y5y from a flat 5% curve", bondmath.forward({"b": [5.0, 0, 0], "lam": 2}, 5, 10), 5.0, 1e-6)
# returns: a day's return is the yield's daily income when nothing moves; a 1% rise in a 10-year yield loses ~8%
check("one day's carry at 5%", perf.day_return(5.0, 5.0, 86400, 10), 0.05 / 365, 1e-9)
check("10-year bond, yield +1%", perf.day_return(5.0, 6.0, 0, 10), -0.0742, 0.003)
# glitch filter: drops a one-day spike that snaps back, keeps a real jump
s = perf.clean([[0, 4.0], [1, 4.02], [2, 9.0], [3, 4.03], [4, 4.05]])
check("glitch removed", len(s), 4, 0)
s = perf.clean([[0, 4.0], [1, 4.02], [2, 6.0], [3, 6.1], [4, 6.05]])
check("real jump kept", len(s), 5, 0)

if FAILS:
    sys.exit(f"{len(FAILS)} check(s) failed: {', '.join(FAILS)}")
print("All checks passed.")
