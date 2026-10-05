"""The government bond markets Bond Compass follows, and where each number comes from.

Each market lists the maturities CNBC quotes. `hist` maturities have a daily
history (CNBC symbol "DE10Y-DE"); `live` ones only have today's quote
(Reuters-style symbol "DE4YT=RR"), which still fills in the shape of the curve.
"""

# code, name, region, currency, IMF code, BIS code (None = no policy-rate feed), coupons a year,
# maturities with history, extra live-only maturities, [lon, lat]
MARKETS = [
    ("US", "United States", "Americas", "USD", "USA", "US", 2,
     "1M 3M 6M 1Y 2Y 3Y 5Y 7Y 10Y 20Y 30Y", "", [-98, 39]),
    ("CA", "Canada", "Americas", "CAD", "CAN", "CA", 2,
     "1M 3M 6M 1Y 2Y 3Y 5Y 10Y 20Y 30Y", "4Y 7Y", [-100, 57]),
    ("BR", "Brazil", "Americas", "BRL", "BRA", "BR", 2, "1Y 2Y 10Y", "3M 6M", [-52, -10]),
    ("MX", "Mexico", "Americas", "MXN", "MEX", "MX", 2, "1Y 3Y 10Y", "30Y", [-102, 23]),
    ("CL", "Chile", "Americas", "CLP", "CHL", "CL", 2, "10Y", "1Y 2Y 4Y", [-71, -33]),
    ("PE", "Peru", "Americas", "PEN", "PER", "PE", 2, "10Y", "", [-75, -10]),
    ("GB", "United Kingdom", "Europe", "GBP", "GBR", "GB", 2,
     "1M 3M 6M 1Y 2Y 3Y 5Y 7Y 10Y 15Y 20Y 30Y", "4Y 6Y 8Y 9Y 25Y 40Y", [-2, 54]),
    ("DE", "Germany", "Europe", "EUR", "DEU", "XM", 1,
     "6M 1Y 2Y 3Y 5Y 7Y 10Y 15Y 20Y 30Y", "3M 4Y 6Y 8Y 9Y", [10, 51]),
    ("FR", "France", "Europe", "EUR", "FRA", "XM", 1,
     "1Y 2Y 3Y 5Y 7Y 10Y 15Y 20Y 30Y", "4Y 6Y 8Y 9Y 50Y", [2, 47]),
    ("IT", "Italy", "Europe", "EUR", "ITA", "XM", 2,
     "6M 1Y 2Y 3Y 5Y 7Y 10Y 15Y 20Y 30Y 50Y", "4Y 6Y 8Y 9Y", [12, 43]),
    ("ES", "Spain", "Europe", "EUR", "ESP", "XM", 1,
     "6M 2Y 3Y 5Y 7Y 10Y 15Y 20Y 30Y", "4Y 6Y 8Y 9Y", [-4, 40]),
    ("NL", "Netherlands", "Europe", "EUR", "NLD", "XM", 1, "2Y 10Y", "", [5, 52]),
    ("BE", "Belgium", "Europe", "EUR", "BEL", "XM", 1,
     "1Y 2Y 3Y 5Y 7Y 10Y 15Y 30Y 50Y", "4Y 6Y 8Y 9Y", [4.5, 50.6]),
    ("AT", "Austria", "Europe", "EUR", "AUT", "XM", 1,
     "1Y 2Y 3Y 5Y 7Y 10Y 15Y 20Y 30Y", "4Y 6Y 8Y 9Y", [14.5, 47.5]),
    ("PT", "Portugal", "Europe", "EUR", "PRT", "XM", 1, "2Y 3Y 5Y 10Y", "", [-8, 39.5]),
    ("GR", "Greece", "Europe", "EUR", "GRC", "XM", 1, "2Y 3Y 10Y", "", [22, 39]),
    ("IE", "Ireland", "Europe", "EUR", "IRL", "XM", 1, "2Y 5Y 10Y", "", [-8, 53]),
    ("FI", "Finland", "Europe", "EUR", "FIN", "XM", 1, "2Y 3Y 5Y 10Y", "4Y", [26, 64]),
    ("CH", "Switzerland", "Europe", "CHF", "CHE", "CH", 1, "2Y 10Y", "", [8, 47]),
    ("SE", "Sweden", "Europe", "SEK", "SWE", "SE", 1, "2Y 10Y", "", [16, 62]),
    ("NO", "Norway", "Europe", "NOK", "NOR", "NO", 1, "3M 6M 1Y 3Y 5Y 7Y 10Y", "", [9, 61]),
    ("PL", "Poland", "Europe", "PLN", "POL", "PL", 1, "1Y 2Y 3Y 5Y 7Y 10Y", "", [19, 52]),
    ("HU", "Hungary", "Europe", "HUF", "HUN", "HU", 1, "1Y 3Y 5Y 10Y 15Y", "", [19.5, 47]),
    ("TR", "Turkey", "Europe", "TRY", "TUR", "TR", 2, "2Y 10Y", "", [35, 39]),
    ("JP", "Japan", "Asia-Pacific", "JPY", "JPN", "JP", 2,
     "3M 6M 2Y 3Y 5Y 10Y 15Y 20Y 30Y", "4Y 6Y 7Y 8Y 9Y 40Y", [138, 37]),
    ("AU", "Australia", "Asia-Pacific", "AUD", "AUS", "AU", 2,
     "1Y 2Y 3Y 5Y 7Y 10Y 15Y", "4Y 6Y 8Y 9Y 12Y 20Y 30Y", [134, -25]),
    ("NZ", "New Zealand", "Asia-Pacific", "NZD", "NZL", "NZ", 2, "1M 3M 6M 1Y 2Y 5Y 10Y", "", [172, -41]),
    ("CN", "China", "Asia-Pacific", "CNY", "CHN", "CN", 1, "2Y 10Y", "1Y 5Y 15Y", [104, 35]),
    ("IN", "India", "Asia-Pacific", "INR", "IND", "IN", 2,
     "10Y 30Y", "1Y 2Y 3Y 4Y 5Y 6Y 7Y 8Y 9Y 12Y 15Y", [79, 22]),
    ("ID", "Indonesia", "Asia-Pacific", "IDR", "IDN", "ID", 2, "10Y 15Y", "1Y 3Y 5Y 20Y 30Y", [118, -2]),
    ("KR", "South Korea", "Asia-Pacific", "KRW", "KOR", "KR", 2, "5Y 10Y 50Y", "1Y 2Y 3Y 4Y 20Y", [128, 36]),
    ("TH", "Thailand", "Asia-Pacific", "THB", "THA", "TH", 2, "10Y", "", [101, 15]),
    ("HK", "Hong Kong", "Asia-Pacific", "HKD", "HKG", "HK", 2, "10Y", "1Y 2Y 3Y 5Y 7Y", [114.2, 22.3]),
    ("SG", "Singapore", "Asia-Pacific", "SGD", "SGP", None, 2, "6M 1Y 2Y 5Y 10Y 15Y 20Y 30Y 50Y", "", [103.8, 1.35]),
    ("MY", "Malaysia", "Asia-Pacific", "MYR", "MYS", "MY", 2, "3Y 5Y 7Y 10Y", "", [102, 4]),
    ("PH", "Philippines", "Asia-Pacific", "PHP", "PHL", "PH", 2, "1M 3M 6M 1Y 2Y 3Y 4Y 5Y 7Y 10Y 20Y 25Y", "", [122, 12]),
    ("ZA", "South Africa", "Middle East & Africa", "ZAR", "ZAF", "ZA", 2, "3M 5Y 10Y 20Y 30Y", "", [24, -29]),
    ("EG", "Egypt", "Middle East & Africa", "EGP", "EGY", None, 2, "3M 1Y", "5Y 10Y", [30, 27]),
    ("NG", "Nigeria", "Middle East & Africa", "NGN", "NGA", None, 2, "10Y", "", [8, 9.5]),
]
EURO = {"DE", "FR", "IT", "ES", "NL", "BE", "AT", "PT", "GR", "IE", "FI"}
DEVELOPED = {"US", "CA", "GB", "DE", "FR", "IT", "ES", "NL", "BE", "AT", "PT", "GR", "IE", "FI", "CH", "SE",
             "JP", "AU", "NZ", "HK", "NO", "SG"}
# Markets whose yields come from official sources other than CNBC (extra_sources.py)
EXTRA = {"NO", "PL", "SG", "MY", "PH", "PE"}
ISO = {"US": "840", "CA": "124", "BR": "076", "MX": "484", "CL": "152", "GB": "826", "DE": "276", "FR": "250",
       "IT": "380", "ES": "724", "NL": "528", "BE": "056", "AT": "040", "PT": "620", "GR": "300", "IE": "372",
       "FI": "246", "CH": "756", "SE": "752", "HU": "348", "TR": "792", "JP": "392", "AU": "036", "NZ": "554",
       "CN": "156", "IN": "356", "ID": "360", "KR": "410", "TH": "764", "HK": "344", "ZA": "710", "EG": "818",
       "NG": "566", "NO": "578", "PL": "616", "SG": "702", "MY": "458", "PH": "608", "PE": "604"}
# The name Wikipedia's list of sovereign credit ratings uses, where it differs from ours
RATING_NAME = {"KR": "South Korea", "HK": "Hong Kong"}


def tenor_years(t):
    return int(t[:-1]) / 12 if t.endswith("M") else float(t[:-1])


def symbol(code, tenor, live_only=False):
    if code in EXTRA:
        return f"{code}{tenor}@X"
    if live_only:
        return f"{code}{tenor}T=RR"
    return f"US{tenor}" if code == "US" else f"{code}{tenor}-{code}"


def points(m):
    """[(tenor, symbol, has_history)] for one market, shortest maturity first."""
    code, hist, live = m[0], m[7].split(), m[8].split()
    pts = [(t, symbol(code, t), True) for t in hist] + [(t, symbol(code, t, True), False) for t in live]
    return sorted(pts, key=lambda p: tenor_years(p[0]))


# Credit and inflation gauges from FRED (St. Louis Fed). ICE BofA spreads: FRED keeps 3 years.
FRED = [
    # id, label, group, kind ("spread" in % points, shown in bp; "yield" in %)
    ("BAMLC0A0CM", "US investment grade", "us", "spread"),
    ("BAMLC0A1CAAA", "AAA", "ladder", "spread"),
    ("BAMLC0A2CAA", "AA", "ladder", "spread"),
    ("BAMLC0A3CA", "A", "ladder", "spread"),
    ("BAMLC0A4CBBB", "BBB", "ladder", "spread"),
    ("BAMLH0A1HYBB", "BB", "ladder", "spread"),
    ("BAMLH0A2HYB", "B", "ladder", "spread"),
    ("BAMLH0A3HYC", "CCC and below", "ladder", "spread"),
    ("BAMLH0A0HYM2", "US high yield", "us", "spread"),
    ("BAMLHE00EHYIOAS", "Euro high yield", "world", "spread"),
    ("BAMLEMIBHGCRPIOAS", "EM investment grade", "world", "spread"),
    ("BAMLEMHBHYCRPIOAS", "EM high yield", "world", "spread"),
    ("BAMLEMCBPIOAS", "EM corporates (all)", "world", "spread"),
    ("BAMLC0A0CMEY", "US investment grade", "yield", "yield"),
    ("BAMLC0A4CBBBEY", "US BBB", "yield", "yield"),
    ("BAMLH0A0HYM2EY", "US high yield", "yield", "yield"),
    ("BAMLEMCBPIEY", "EM corporates", "yield", "yield"),
    ("DFII5", "5-year TIPS real yield", "real", "yield"),
    ("DFII10", "10-year TIPS real yield", "real", "yield"),
    ("DFII30", "30-year TIPS real yield", "real", "yield"),
    ("T5YIE", "5-year breakeven inflation", "infl", "yield"),
    ("T10YIE", "10-year breakeven inflation", "infl", "yield"),
    ("T5YIFR", "5-year, 5-year forward inflation", "infl", "yield"),
]

# IMF series (DataMapper API): World Economic Outlook, plus the Fiscal Monitor for the budget detail
IMF = {
    "GGXWDG_NGDP": "debt",              # general government gross debt, % of GDP (WEO)
    "GGXWDN_G01_GDP_PT": "netDebt",     # net debt, % of GDP (Fiscal Monitor)
    "GGXCNL_G01_GDP_PT": "balance",     # overall budget balance, % of GDP (Fiscal Monitor)
    "GGXONLB_G01_GDP_PT": "primary",    # primary balance (before interest), % of GDP (Fiscal Monitor)
    "GGR_G01_GDP_PT": "revenue",        # government revenue, % of GDP (Fiscal Monitor)
    "NGDP_RPCH": "growth",              # real GDP growth, % (WEO)
    "PCPIPCH": "inflation",             # consumer-price inflation, annual average % (WEO)
    "BCA_NGDPD": "current",             # current account balance, % of GDP (WEO)
    "LUR": "unemployment",              # unemployment rate, % (WEO)
    "NGDPD": "gdpUsd",                  # GDP, US$ billions (WEO)
}

# Bank of England daily curves (IADB): UK zero-coupon nominal, real (index-linked) and implied inflation (RPI)
BOE = [
    ("IUDSRZC", "UK 5-year real yield", "ukreal", "yield"),
    ("IUDMRZC", "UK 10-year real yield", "ukreal", "yield"),
    ("IUDLRZC", "UK 20-year real yield", "ukreal", "yield"),
    ("IUDSIZC", "UK 5-year implied inflation (RPI)", "ukinfl", "yield"),
    ("IUDMIZC", "UK 10-year implied inflation (RPI)", "ukinfl", "yield"),
    ("IUDLIZC", "UK 20-year implied inflation (RPI)", "ukinfl", "yield"),
]

YAHOO = ["^MOVE", "GBP=X"]  # bond-market volatility (MOVE index); pounds per US dollar


# Which London-listed fund groups (data/etfs.json) give a UK investor exposure to each market's government bonds
def fund_groups(code, dm):
    if code == "GB":
        return ["UK gilts", "Short-dated gilts", "Long-dated gilts", "UK index-linked gilts"]
    if code == "US":
        return ["US Treasuries"]
    if code in EURO:
        return ["Euro-area government bonds"]
    if code == "JP":
        return ["Japanese government bonds"]
    if not dm:
        return ["EM government bonds, local currency"]
    return ["Global government bonds GBP-hedged"]
