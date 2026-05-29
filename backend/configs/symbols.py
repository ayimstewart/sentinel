# ETF Universe — this is ALL we trade

# Market condition filters (not traded)
MARKET_FILTERS = ['SPY', 'QQQ', 'IWM']

# Tradeable ETFs
TRADEABLE_ETFS = [
    'SMH',   # Semiconductors
    'XLK',   # Technology
    'CIBR',  # Cybersecurity
    'VUG',   # Growth
    'URA',   # Uranium/Nuclear
    'IWM',   # Small caps
]

ALL_ETFS = list(
    dict.fromkeys(MARKET_FILTERS + TRADEABLE_ETFS)
)
