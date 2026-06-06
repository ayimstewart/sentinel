def calculate(
    entry: float,
    stop: float,
    portfolio_value: float,
    atr_pct: float = 2.0,
    regime: str = 'NEUTRAL',
    drawdown_mult: float = 1.0,
    max_positions: int = 3,
) -> dict | None:

    if entry <= 0 or stop <= 0 or stop >= entry:
        return None
    if portfolio_value <= 0:
        return None

    # 2% risk per trade
    risk_amount = portfolio_value * 0.02

    vol_mult = (
        0.5 if atr_pct > 4 else
        0.65 if atr_pct > 3 else
        0.8 if atr_pct > 2 else
        1.0
    )

    regime_mult = {
        'BULLISH': 1.0,
        'NEUTRAL': 0.75,
        'BEARISH': 0.5,
    }.get(regime, 0.75)

    risk_amount = (
        risk_amount * vol_mult *
        regime_mult * drawdown_mult
    )

    risk_per_share = entry - stop
    shares = risk_amount / risk_per_share

    # Cap at 1/max_positions of portfolio
    max_cost = portfolio_value / max_positions
    max_shares = max_cost / entry
    shares = min(shares, max_shares)

    if shares < 0.01:
        return None

    cost = round(shares * entry, 2)

    # Hard cap: never more than 40% on one trade
    if cost > portfolio_value * 0.4:
        shares = (portfolio_value * 0.4) / entry
        cost = round(shares * entry, 2)

    return {
        'shares': round(shares, 4),
        'cost': cost,
        'risk_amount': round(risk_amount, 2),
        'risk_per_share': round(risk_per_share, 2),
        'pct_of_portfolio': round(
            cost / portfolio_value * 100, 1
        ),
    }
