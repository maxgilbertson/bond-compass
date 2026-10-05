"""Returns rebuilt from yields: what a bond earned, in its own currency or hedged back to pounds.

Bonds don't come with a free daily price index, but a bond that is rolled to stay (say) 10 years
from maturity earns, each day, its yield for the day, loses duration x the rise in yield (or gains
from a fall), plus a convexity term. Hedging the currency back to pounds adds the gap between the
UK and the local short-term interest rates. The practice portfolios and the past-data test both
use these functions, so they measure returns the same way.
"""
import bisect

import bondmath

DAY = 86400
YEAR = 365 * DAY


def at_or_before(series, ts):
    """Value of a sorted [[t, v], ...] series on or just before ts (None before it starts)."""
    lo, hi = 0, len(series)
    while lo < hi:
        mid = (lo + hi) // 2
        if series[mid][0] <= ts:
            lo = mid + 1
        else:
            hi = mid
    return series[lo - 1][1] if lo else None


def window(series, times, a, b):
    """The part of a series from just before time a to time b (times = the series' timestamps)."""
    i, j = bisect.bisect_left(times, a), bisect.bisect_right(times, b)
    return series[max(0, i - 1):j]


def last_point(series, times, ts):
    i = bisect.bisect_right(times, ts) - 1
    return series[i] if i >= 0 else None


def clean(series):
    """Drop one-day glitches: a close that jumps far from its neighbours and snaps straight back.

    A real move (a crisis, a policy shock) doesn't reverse the next day, so it is kept.
    """
    if len(series) < 3:
        return series
    out = [series[0]]
    for k in range(1, len(series) - 1):
        prev, cur, nxt = out[-1][1], series[k][1], series[k + 1][1]
        jump = abs(cur - prev)
        limit = max(0.6, 0.2 * abs(prev))
        if jump > limit and abs(nxt - prev) < jump * 0.3:
            continue
        out.append(series[k])
    out.append(series[-1])
    return out


def day_return(a, b, dt, yrs):
    """One period's return of a constant-maturity bond whose yield went from a to b (in %) over dt seconds."""
    mod, conv = bondmath.par_duration(a, yrs)
    dy = (b - a) / 100
    return a / 100 * dt / YEAR - mod * dy + 0.5 * conv * dy * dy


def index(h, start, end=None, yrs=10.0, cash_local=None, cash_home=None):
    """Daily value of 1 invested at `start` in a constant-maturity bond, from its yield history h = [[t, y]].

    With cash_local and cash_home (functions t -> % rate), the currency is hedged into the home currency:
    each day also earns (home rate - local rate). Returns [[t, value], ...] starting at [start, 1.0],
    or None if the history doesn't reach back to start.
    """
    pts = [p for p in h if p[0] <= (end or float("inf"))]
    base = at_or_before(pts, start)
    if base is None:
        return None
    seq = [[start, base]] + [p for p in pts if p[0] > start]
    out, v = [[start, 1.0]], 1.0
    for (t0, a), (t1, b) in zip(seq, seq[1:]):
        dt = t1 - t0
        r = day_return(a, b, dt, yrs)
        if cash_local and cash_home:
            cl, ch = cash_local(t0), cash_home(t0)
            if cl is not None and ch is not None:
                r += (ch - cl) / 100 * dt / YEAR
        v *= 1 + r
        out.append([t1, v])
    return out


def rate_fn(*series, fallback=None):
    """A function t -> rate from one or more [[t, rate]] series (the first that covers t), else `fallback`."""
    def f(t):
        for s in series:
            if s and s[0][0] <= t:
                v = at_or_before(s, t)
                if v is not None:
                    return v
        return fallback
    return f
