import numpy as np
import logging
from typing import List
from backend.backtest.engine import (
    BacktestTrade, BacktestResult
)

logger = logging.getLogger(__name__)

def compute_metrics(
    ticker: str,
    strategy: str,
    trades: List[BacktestTrade],
    equity_curve: List[float],
    initial_capital: float
) -> BacktestResult:

    if not trades:
        return BacktestResult(
            ticker=ticker,
            strategy=strategy,
            period='1y',
            initial_capital=initial_capital,
            final_value=initial_capital,
            total_trades=0,
            wins=0,
            losses=0,
            win_rate=0.0,
            total_return_pct=0.0,
            profit_factor=0.0,
            max_drawdown_pct=0.0,
            sharpe_ratio=0.0,
            expectancy=0.0,
            avg_win=0.0,
            avg_loss=0.0,
            avg_hold_days=0.0,
            best_trade=0.0,
            worst_trade=0.0,
            trades=[]
        )

    pnls = [t.pnl for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    win_rate = (
        len(wins) / len(pnls) * 100
        if pnls else 0
    )

    gross_profit = sum(wins) if wins else 0
    gross_loss = abs(sum(losses)) if losses else 1
    profit_factor = round(
        gross_profit / gross_loss, 2
    )

    avg_win = round(
        np.mean(wins), 2
    ) if wins else 0
    avg_loss = round(
        abs(np.mean(losses)), 2
    ) if losses else 0

    expectancy = round(
        (win_rate/100 * avg_win) -
        ((1 - win_rate/100) * avg_loss), 2
    )

    # Max drawdown
    peak = equity_curve[0]
    max_dd = 0.0
    for val in equity_curve:
        if val > peak:
            peak = val
        if peak > 0:
            dd = (peak - val) / peak * 100
            if dd > max_dd:
                max_dd = dd

    # Sharpe ratio
    if len(equity_curve) > 1:
        returns = np.diff(equity_curve) / \
                  np.array(equity_curve[:-1])
        sharpe = (
            np.mean(returns) /
            np.std(returns) *
            np.sqrt(252)
        ) if np.std(returns) > 0 else 0
    else:
        sharpe = 0

    final = equity_curve[-1] if equity_curve else initial_capital
    total_return = (
        (final - initial_capital) /
        initial_capital * 100
    )

    hold_days = [t.hold_days for t in trades]

    return BacktestResult(
        ticker=ticker,
        strategy=strategy,
        period='1y',
        initial_capital=initial_capital,
        final_value=round(final, 2),
        total_trades=len(trades),
        wins=len(wins),
        losses=len(losses),
        win_rate=round(win_rate, 1),
        total_return_pct=round(total_return, 1),
        profit_factor=profit_factor,
        max_drawdown_pct=round(max_dd, 1),
        sharpe_ratio=round(sharpe, 2),
        expectancy=expectancy,
        avg_win=avg_win,
        avg_loss=avg_loss,
        avg_hold_days=round(
            np.mean(hold_days), 1
        ) if hold_days else 0,
        best_trade=round(max(pnls), 2),
        worst_trade=round(min(pnls), 2),
        trades=trades
    )
