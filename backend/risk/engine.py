from dataclasses import dataclass
from typing import Optional
from backend.strategies.scanner import Signal

# Risk parameters — change here only
MAX_POSITIONS = 3
MAX_RISK_PCT = 0.02        # 2% per trade
MAX_DAILY_LOSS_PCT = 0.05  # 5% daily limit
MAX_SECTOR_POSITIONS = 1   # 1 ETF per sector
MIN_ATR_PCT = 0.01         # 1% minimum movement

# Sector mapping
SECTORS = {
    'SMH': 'semiconductors',
    'XLK': 'technology',
    'CIBR': 'cybersecurity',
    'VUG': 'growth',
    'URA': 'nuclear',
    'IWM': 'small_caps',
    'SPY': 'broad_market',
    'QQQ': 'broad_market',
}


@dataclass
class RiskDecision:
    allowed: bool
    reason: str
    shares: float = 0.0
    position_value: float = 0.0
    risk_amount: float = 0.0
    stop_price: float = 0.0


@dataclass
class Portfolio:
    positions: list         # list of open positions
    portfolio_value: float  # total account value
    cash: float             # available cash
    daily_pnl: float        # today's PnL


def evaluate(
    signal: Signal,
    portfolio: Portfolio,
) -> RiskDecision:

    # Gate 1 — max positions
    if len(portfolio.positions) >= MAX_POSITIONS:
        return RiskDecision(
            allowed=False,
            reason=f"Max {MAX_POSITIONS} positions reached",
        )

    # Gate 2 — daily loss limit
    if portfolio.portfolio_value > 0:
        daily_loss_pct = (
            portfolio.daily_pnl / portfolio.portfolio_value
        )
        if daily_loss_pct <= -MAX_DAILY_LOSS_PCT:
            return RiskDecision(
                allowed=False,
                reason=(
                    f"Daily loss limit hit: "
                    f"{daily_loss_pct * 100:.1f}%"
                ),
            )

    # Gate 3 — no duplicate positions
    held_tickers = [p['ticker'] for p in portfolio.positions]
    if signal.ticker in held_tickers:
        return RiskDecision(
            allowed=False,
            reason=f"Already holding {signal.ticker}",
        )

    # Gate 4 — sector exposure
    new_sector = SECTORS.get(signal.ticker)
    if new_sector:
        held_sectors = [
            SECTORS.get(p['ticker'])
            for p in portfolio.positions
        ]
        if held_sectors.count(new_sector) >= MAX_SECTOR_POSITIONS:
            return RiskDecision(
                allowed=False,
                reason=f"Sector {new_sector} already at max",
            )

    # Gate 5 — calculate position size
    sizing = _calculate_size(
        signal=signal,
        portfolio_value=portfolio.portfolio_value,
        cash=portfolio.cash,
    )

    if not sizing:
        return RiskDecision(
            allowed=False,
            reason="Cannot calculate safe position size",
        )

    shares, cost, risk = sizing

    # Gate 6 — enough cash
    if cost > portfolio.cash:
        return RiskDecision(
            allowed=False,
            reason=(
                f"Insufficient cash: need ${cost:.2f} "
                f"have ${portfolio.cash:.2f}"
            ),
        )

    return RiskDecision(
        allowed=True,
        reason="All risk checks passed",
        shares=shares,
        position_value=cost,
        risk_amount=risk,
        stop_price=signal.stop,
    )


def _calculate_size(
    signal: Signal,
    portfolio_value: float,
    cash: float,
) -> Optional[tuple]:

    if portfolio_value <= 0:
        return None

    entry = signal.entry
    stop = signal.stop

    if entry <= 0 or stop <= 0 or stop >= entry:
        return None

    risk_amount = portfolio_value * MAX_RISK_PCT

    risk_per_share = entry - stop
    if risk_per_share <= 0:
        return None

    shares = risk_amount / risk_per_share

    # Cap at 33% of portfolio
    max_cost = portfolio_value * 0.33
    max_shares = max_cost / entry
    shares = min(shares, max_shares)

    if shares < 0.01:
        return None

    cost = round(shares * entry, 2)
    shares = round(shares, 4)
    risk = round(risk_amount, 2)

    return shares, cost, risk


def get_sector(ticker: str) -> str:
    return SECTORS.get(ticker, 'unknown')
