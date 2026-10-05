"""Bond arithmetic: price from yield, duration, convexity, DV01, curve interpolation and roll-down.

Conventions are simplified the same way for every market (actual/actual day count,
the market's usual coupon frequency, settlement today), which is close enough to the
official figures for comparing bonds, but not for settling a trade.
"""
import bisect
import math
from datetime import date


def _add_months(d, months):
    y, m = divmod(d.month - 1 + months, 12)
    y, m = d.year + y, m + 1
    for day in (d.day, 30, 29, 28):
        try:
            return date(y, m, day)
        except ValueError:
            continue


def analytics(y, coupon, maturity, freq, today=None):
    """Price and risk of one bond from its yield (%), annual coupon (%) and maturity date.

    Returns dirty and clean price per 100, accrued interest, Macaulay and modified duration (years),
    convexity, DV01 per 1 million of face value (in the bond's currency) and years to maturity.
    A missing coupon is treated as a zero-coupon bill.
    """
    today = today or date.today()
    if maturity is None or maturity <= today or y is None:
        return None
    yrs = (maturity - today).days / 365.25
    yf = y / 100
    if not coupon:
        # bill or zero-coupon: one payment of 100 at maturity
        disc = (1 + yf) ** yrs
        dirty = 100 / disc
        mac = yrs
        mod = yrs / (1 + yf)
        conv = yrs * (yrs + 1) / (1 + yf) ** 2
        return _pack(dirty, dirty, 0.0, mac, mod, conv, yrs)
    f = freq
    step = 12 // f
    # coupon dates, walking back from maturity
    dates = [maturity]
    while dates[-1] > today:
        dates.append(_add_months(maturity, -step * len(dates)))
    prev, nxt = dates[-1], dates[-2]
    dates = sorted(dates[:-1])  # future coupon dates, earliest first
    w = (nxt - today).days / max(1, (nxt - prev).days)  # fraction of a coupon period until the next coupon
    c = coupon / f
    r = yf / f
    pv = cf_t = cf_t2 = 0.0
    n = len(dates)
    for k in range(n):
        t = k + w  # in coupon periods
        cf = c + (100 if k == n - 1 else 0)
        disc = (1 + r) ** t
        pv += cf / disc
        cf_t += t * cf / disc
        cf_t2 += t * (t + 1) * cf / disc
    accrued = c * (1 - w)
    mac = cf_t / pv / f
    mod = mac / (1 + r)
    conv = cf_t2 / pv / f ** 2 / (1 + r) ** 2
    return _pack(pv, pv - accrued, accrued, mac, mod, conv, yrs)


def _pack(dirty, clean, accrued, mac, mod, conv, yrs):
    return {"dirty": dirty, "clean": clean, "accrued": accrued, "mac": mac, "mod": mod, "conv": conv,
            "dv01": dirty / 100 * 1_000_000 * mod * 0.0001, "yrs": yrs}


def par_duration(y, yrs, freq=2):
    """Modified duration and convexity of a bond priced at par (coupon = yield), for history approximations."""
    if yrs <= 0:
        return 0.0, 0.0
    r = max(y, 0.01) / 100 / freq
    n = max(1, round(yrs * freq))
    c = r * 100
    pv = cf_t = cf_t2 = 0.0
    for k in range(1, n + 1):
        cf = c + (100 if k == n else 0)
        disc = (1 + r) ** k
        pv += cf / disc
        cf_t += k * cf / disc
        cf_t2 += k * (k + 1) * cf / disc
    mod = cf_t / pv / freq / (1 + r)
    conv = cf_t2 / pv / freq ** 2 / (1 + r) ** 2
    return mod, conv


class Curve:
    """A yield curve through (years, yield) points: straight lines between points, flat beyond the ends."""

    def __init__(self, pts):
        pts = sorted((x, y) for x, y in pts if x is not None and y is not None)
        self.x = [p[0] for p in pts]
        self.y = [p[1] for p in pts]

    def __bool__(self):
        return bool(self.x)

    def at(self, x):
        if not self.x:
            return None
        if x <= self.x[0]:
            return self.y[0]
        if x >= self.x[-1]:
            return self.y[-1]
        i = bisect.bisect_right(self.x, x)
        x0, x1, y0, y1 = self.x[i - 1], self.x[i], self.y[i - 1], self.y[i]
        return y0 + (y1 - y0) * (x - x0) / (x1 - x0) if x1 > x0 else y0

    def covers(self, x, slack=0.6):
        """True if x lies within the quoted maturities (or close to an end), so the value isn't a guess."""
        return bool(self.x) and self.x[0] - slack <= x <= self.x[-1] + slack


def outliers(pts, limit=0.5):
    """Indexes of curve points that sit far off the line through their neighbours (likely a bad or stale quote).

    pts: [(years, yield)] sorted by years. A point is flagged when it is more than `limit` percentage points
    (50bp), or 12% of the yield if that is bigger, away from the straight line between the points on either side.
    """
    bad = set()
    for i in range(1, len(pts) - 1):
        (x0, y0), (x1, y1), (x2, y2) = pts[i - 1], pts[i], pts[i + 1]
        if x2 <= x0:
            continue
        line = y0 + (y2 - y0) * (x1 - x0) / (x2 - x0)
        if abs(y1 - line) > max(limit, abs(line) * 0.12):
            bad.add(i)
    return bad


# ---------------------------------------------------------------- fitted curve (Nelson-Siegel) and forward rates

def _ns_terms(t, lam):
    x = max(t, 1e-6) / lam
    e = math.exp(-x)
    f1 = (1 - e) / x
    return 1.0, f1, f1 - e


def _solve3(a, b):
    """Solve a 3x3 linear system by Gaussian elimination (a is a list of rows)."""
    m = [row[:] + [v] for row, v in zip(a, b)]
    for i in range(3):
        p = max(range(i, 3), key=lambda r: abs(m[r][i]))
        if abs(m[p][i]) < 1e-12:
            return None
        m[i], m[p] = m[p], m[i]
        for r in range(3):
            if r != i:
                f = m[r][i] / m[i][i]
                m[r] = [x - f * y for x, y in zip(m[r], m[i])]
    return [m[i][3] / m[i][i] for i in range(3)]


def fit_curve(pts):
    """A smooth Nelson-Siegel curve through (years, yield) points: level, slope and hump, with the hump's
    position chosen from a grid. Returns {"b": [b0, b1, b2], "lam": lam, "rmse": %} or None (fewer than 5 points)."""
    pts = [(x, y) for x, y in pts if x is not None and y is not None and x > 0]
    if len(pts) < 5:
        return None
    best = None
    for lam in (0.4, 0.6, 0.8, 1.0, 1.3, 1.7, 2.2, 2.8, 3.5, 4.5, 6.0, 8.0):
        X = [_ns_terms(t, lam) for t, _ in pts]
        xtx = [[sum(r[i] * r[j] for r in X) + (1e-6 if i == j else 0) for j in range(3)] for i in range(3)]
        xty = [sum(r[i] * y for r, (_, y) in zip(X, pts)) for i in range(3)]
        b = _solve3(xtx, xty)
        if not b:
            continue
        sse = sum((y - sum(bi * xi for bi, xi in zip(b, r))) ** 2 for r, (_, y) in zip(X, pts))
        if best is None or sse < best[0]:
            best = (sse, b, lam)
    if not best:
        return None
    return {"b": best[1], "lam": best[2], "rmse": math.sqrt(best[0] / len(pts))}


def curve_at(fit, t):
    return sum(b * x for b, x in zip(fit["b"], _ns_terms(t, fit["lam"])))


def forward(fit, a, b):
    """Rate for borrowing from year a to year b implied by the fitted curve (yields treated as annual zero rates)."""
    ya, yb = curve_at(fit, a) / 100, curve_at(fit, b) / 100
    if a <= 0:
        return yb * 100
    return (((1 + yb) ** b / (1 + ya) ** a) ** (1 / (b - a)) - 1) * 100
