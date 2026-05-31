# ETF Universe — this is ALL we trade

# Market condition filters (not traded)
MARKET_FILTERS = ['SPY', 'QQQ', 'IWM']

# Priority ranking by proven backtest edge (2y)
PRIORITY_ETFS = [
    # Backtest 2y: WR=66% PF=4.56 Sharpe=2.56
    'XLK',   # Best edge — 66% WR Sharpe 2.56
    # Backtest 2y: WR=54% PF=3.14 Sharpe=1.43
    'IWM',   # Good edge — 54% WR Sharpe 1.43
    # Backtest 2y: WR=66% PF=2.10 Sharpe=0.91
    'VUG',   # Decent — 66% WR low trades
    # Backtest 2y: WR=60% PF=1.87 Sharpe=0.74
    'CIBR',  # Decent — 60% WR low trades
    # Backtest 2y: WR=42% PF=1.12 Sharpe=0.38
    'SMH',   # Weak — 42% WR watch only
    # Backtest 2y: WR=33% PF=0.61 Sharpe=-0.22
    'URA',   # Poor — negative return last
]

TRADEABLE_ETFS = PRIORITY_ETFS

ALL_ETFS = list(
    dict.fromkeys(MARKET_FILTERS + TRADEABLE_ETFS)
)

# Extended universe from ranker (30+ ETFs)
from backend.strategies.ranker import (  # noqa: E402
    ETF_UNIVERSE,
    TRADEABLE,
)
