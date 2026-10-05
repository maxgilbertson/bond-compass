# Bond Compass

A live tracker of the world's government bond markets: 39 countries' yield curves (plus six more with monthly data),
trader-grade analytics for every maturity, the public finances behind each government, every UK gilt after tax,
a tested score and a live track record, on one page with eleven tabs.

- **Overview**: the yields the world prices from (US, UK, German, Japanese 10-years), the US curve, French and Italian
  spreads over Germany, bond volatility (MOVE) and US high-yield spreads; a rules-based read of the backdrop
  (yields, curves, credit, volatility, inflation expectations, central banks); four shortlists; today's biggest moves;
  value-vs-safety map of all markets.
- **Monitor**: one sortable table, any maturity (benchmark, 2, 5, 10 or 30-year), eight column sets: key numbers,
  yield moves (1 day to 3 years, 1-year range, z-score, 3-year percentile), bond and risk (coupon, maturity, price,
  modified duration, convexity, DV01, volatility), carry (cash rate, roll-down, 12-month return if the curve is
  unchanged, excess over cash, cushion, yields hedged into £ and $, market rate expectations), spreads and real
  yields (vs Treasuries, Bunds and gilts), public finances, returns (local, in £ unhedged and hedged) and the score's parts.
- **Curves**: overlay up to five countries' curves, or one country's curve today vs 1 week, 1 month, 3 months and
  1 year ago; every slope (3m10y, 2s10s, 5s30s, 10s30s, butterfly) and what the market expects from its central bank;
  a country-by-maturity yield matrix (levels, daily, monthly and yearly changes, z-scores).
- **Countries**: world map coloured by any number; a relative-value scatter with any two numbers and a best-fit line
  (e.g. rating vs real yield: who pays more than their rating suggests); where the IMF expects debt to go; interest
  as a share of revenue; the debt arithmetic (r − g, the primary balance needed to hold debt steady, the budget gap,
  average cost of existing debt vs today's yields).
- **Credit & inflation**: US, euro and emerging-market corporate spreads, the spread for each rating from AAA to CCC,
  all-in corporate yields, US TIPS real yields, breakeven inflation and the 5-year, 5-year forward, MOVE history.
- **Central banks**: 21 policy rates, last move, 1-year and 3-month changes, real policy rates, and what 2-year
  yields say markets expect next; chart of any five.
- **UK gilts**: every gilt in issue from the Debt Management Office's daily prices, with yield, after-tax yield at
  0/20/40/45% (coupons are taxed, the gain to £100 isn't), the taxable-equivalent yield, distance from the fitted gilt
  curve and duration; plus UK real yields and implied inflation from the Bank of England.
- **Portfolio**: enter holdings in pounds (hedged or not) for yield, duration, pounds per basis point, currency risk
  and ten shock scenarios; plus 38 London-listed bond funds with fees, prices and returns ("ways to buy").
- **Briefing**: a plain-English weekly round-up, written every Saturday from that week's numbers.
- **Track record**: the score tested on the past (monthly since 2017, hedged into pounds, also for developed markets
  alone), practice portfolios from 5 Oct 2026, and every signal change.
- **Guide**: a five-minute routine, a glossary, how the score works, notes for a UK investor, sources, data health and limits.

Also: a fitted (Nelson-Siegel) curve for each country with each bond's distance from it and forward rates; the
spread between any two markets over time; a calendar of central-bank decisions and key data; daily alerts posted as
a GitHub issue; bond-maths checks before every publish.

Click any country for its detail panel: a rules-based verdict, what stands out, the score's ingredients, every
maturity's full analytics, the curve, yield history since 2016 (and spreads vs Treasuries or Bunds, and 2s10s),
public finances with IMF forecasts, and its ratings and central-bank rate.

**The score** ranks each market's benchmark bond 0–100 against the others: value 60% (real yield 25%, cushion
against rising yields 20%, cheapness vs its own 3 years 15%) and safety 40% (credit rating 15%, debt 10%, budget gap
10%, interest bill 5%). The 75% that can be rebuilt from data known at the time is tested monthly since 2017 (Track
record tab); real yield and the cushion did the work there.

**Live site:** https://maxgilbertson.github.io/bond-compass/ (updated every ~15 minutes by GitHub Actions)

## Where the data comes from

| What | Source | Refreshed |
|---|---|---|
| Yields, coupons, maturities, prices | CNBC quotes (Tradeweb and dealer feeds) | every build (~15 min) |
| Yield history since 2016 | CNBC daily closes, plus our own daily record (`data/history/`) | daily |
| Public finances (debt, deficits, interest, growth, inflation) | IMF World Economic Outlook and Fiscal Monitor | weekly (IMF updates April and October) |
| Central-bank policy rates | Bank for International Settlements | twice a day |
| Corporate spreads, TIPS, breakevens | FRED (ICE BofA indices, US Treasury) | every 4 hours |
| MOVE index, currencies | Yahoo Finance | every build |
| S&P, Moody's and Fitch ratings | Wikipedia's maintained table (`data/ratings.json` is the fallback) | weekly |
| Norway, Poland, Singapore, Malaysia, Philippines, Peru | Norges Bank, BondSpot fixing, MAS, Bank Negara, ADB AsianBondsOnline, BCRP | daily |
| Israel, Colombia, Czech Rep., Denmark, Romania, Taiwan | Bank of Israel, Banco de la República, ECB, CBC Taiwan | monthly |
| Every UK gilt | UK Debt Management Office, report D10B (`gilts.yml`, one request a weekday) | daily |
| UK real yields, implied inflation | Bank of England yield curves (IADB) | every 6 hours |
| Bond fund prices | Yahoo Finance (fees from providers' pages, `data/etfs.json`) | hourly |
| Calendar | Central banks' and statistics offices' schedules (`data/calendar.json`) | update by hand yearly |

Slow-moving data is cached in `data/cache/` (kept between GitHub runs); if a source is down the last good copy is used.
`data/seed/` holds a starter copy of the IMF data in case the IMF's site turns away GitHub's servers.

## Folders

- `app/`: the code and the page.
  - `markets.py`: the 33 markets, which maturities each quotes, and the FRED and IMF series.
  - `sources.py`: fetching and caching from every source.
  - `bondmath.py`: price, duration, convexity, DV01, curve interpolation, roll-down.
  - `bonds.py`: builds everything the page shows, including the score and the backdrop rules.
  - `extra_sources.py`, `monthly_sources.py`: the official sources for markets CNBC doesn't cover.
  - `snapshot.py` + `tracking.py`: the daily record of yields and scores, signal log and practice portfolios.
  - `perf.py` + `backtest.py`: returns rebuilt from yields, and the score tested on the past.
  - `gilts.py`: every UK gilt's yield and after-tax yield. `briefing.py` + `BRIEFING_PROMPT.md`: the weekly briefing.
  - `alerts.py`: the daily alert note. `selftest.py`: bond-maths checks run before every publish.
  - `index.html`, `common.css`, `common.js`: the page.
  - `server.py`: the local web server. `build_static.py`: builds the GitHub Pages copy.
- `data/`: `history/` (daily yields and scores), `paper/` (practice portfolios), `briefings/`, `gilts.json`,
  `etfs.json`, `calendar.json`, `ratings.json`, `seed/`.
- `.github/workflows/`: `deploy.yml` publishes every ~15 minutes (after `selftest.py`); `daily.yml` saves the day's
  record, makes the monthly practice picks and posts alerts; `gilts.yml` fetches gilt prices each weekday afternoon;
  `briefing.yml` gathers the briefing's facts on Saturday mornings (a scheduled Claude task on Max's PC writes it up).

## Run it on your own PC (optional)

The live site needs nothing on your PC. To run a copy locally (Python 3.10+, no packages needed):

```
py app/server.py          # http://localhost:8766, refreshes every 5 minutes
py app/server.py --lan    # also reachable from phones on the same Wi-Fi
```

For research and education only; not investment advice.
