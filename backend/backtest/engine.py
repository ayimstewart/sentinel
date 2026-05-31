import pandas as pd
import numpy as np
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

SLIPPAGE = 0.001   # 0.1% per trade
COMMISSION = 0.0   # free on Alpaca/Robinhood

@dataclass
class BacktestTrade:
    ticker: str
    strategy: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    shares: float
    pnl: float
    pnl_pct: float
    exit_reason: str
    hold_days: int

@dataclass
class BacktestResult:
    ticker: str
    strategy: str
    period: str
    initial_capital: float
    final_value: float
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    total_return_pct: float
    profit_factor: float
    max_drawdown_pct: float
    sharpe_ratio: float
    expectancy: float
    avg_win: float
    avg_loss: float
    avg_hold_days: float
    best_trade: float
    worst_trade: float
    trades: List[BacktestTrade]

class BacktestEngine:
    def __init__(self,
                 initial_capital: float = 300.0,
                 stop_pct: float = 0.03,
                 target1_pct: float = 0.08,
                 target2_pct: float = 0.15,
                 max_hold_days: int = 10,
                 risk_pct: float = 0.02):

        self.initial_capital = initial_capital
        self.stop_pct = stop_pct
        self.target1_pct = target1_pct
        self.target2_pct = target2_pct
        self.max_hold_days = max_hold_days
        self.risk_pct = risk_pct

    def run(self,
            ticker: str,
            df: pd.DataFrame,
            spy_df: pd.DataFrame,
            strategy_name: str = 'ALL'
            ) -> Optional[BacktestResult]:

        if df is None or len(df) < 200:
            logger.warning(
                f"Not enough data for {ticker}"
            )
            return None

        capital = self.initial_capital
        position = None
        trades = []
        equity_curve = []

        from backend.strategies.scanner import (
            calculate_indicators,
            ema_trend_ride,
            breakout_confirmation,
            relative_strength_trend,
        )

        for i in range(50, len(df)):
            date = df.index[i]
            date_str = str(date.date())

            # No lookahead — only use data up to i
            slice_df = df.iloc[:i+1]
            spy_slice = spy_df.iloc[:i+1]

            ind = calculate_indicators(slice_df)
            spy_ind = calculate_indicators(spy_slice)

            if not ind or not spy_ind:
                continue

            price = ind['close']

            # Check exits first
            if position:
                hold = i - position['bar_index']
                exit_reason = None
                exit_price = price

                # Stop loss
                if price <= position['stop']:
                    exit_reason = 'stop_loss'
                    exit_price = price * (
                        1 - SLIPPAGE
                    )

                # Target 1 hit
                elif (price >= position['target1']
                      and not position[
                          'partial_sold'
                      ]):
                    position['partial_sold'] = True
                    position['stop'] = (
                        position['entry']
                    )
                    half = position['shares'] / 2
                    proceeds = half * price * (
                        1 - SLIPPAGE
                    )
                    capital += proceeds
                    position['shares'] -= half

                    pnl = proceeds - (
                        half * position['entry']
                    )
                    trades.append(BacktestTrade(
                        ticker=ticker,
                        strategy=position[
                            'strategy'
                        ],
                        entry_date=position['date'],
                        exit_date=date_str,
                        entry_price=position['entry'],
                        exit_price=price,
                        shares=half,
                        pnl=round(pnl, 2),
                        pnl_pct=round(
                            pnl / (half *
                            position['entry'])
                            * 100, 2
                        ),
                        exit_reason='target1',
                        hold_days=hold
                    ))

                # Target 2 hit
                elif price >= position['target2']:
                    exit_reason = 'target2'
                    exit_price = price * (
                        1 - SLIPPAGE
                    )

                # Max hold time
                elif hold >= self.max_hold_days:
                    exit_reason = 'time_exit'
                    exit_price = price * (
                        1 - SLIPPAGE
                    )

                # Trailing stop after 4% gain
                elif (price - position['entry']
                      ) / position['entry'] >= 0.04:
                    trail = price * 0.98
                    if price <= trail:
                        exit_reason = (
                            'trailing_stop'
                        )
                        exit_price = price * (
                            1 - SLIPPAGE
                        )

                if exit_reason:
                    pnl = (
                        exit_price -
                        position['entry']
                    ) * position['shares']
                    capital += (
                        position['shares'] *
                        exit_price
                    )

                    trades.append(BacktestTrade(
                        ticker=ticker,
                        strategy=position[
                            'strategy'
                        ],
                        entry_date=position['date'],
                        exit_date=date_str,
                        entry_price=position['entry'],
                        exit_price=exit_price,
                        shares=position['shares'],
                        pnl=round(pnl, 2),
                        pnl_pct=round(
                            pnl / (position['shares']
                            * position['entry'])
                            * 100, 2
                        ),
                        exit_reason=exit_reason,
                        hold_days=hold
                    ))
                    position = None

            # Check entries
            if not position:
                signal = None

                if strategy_name in (
                    'EMA_RIDE', 'ALL'
                ):
                    signal = ema_trend_ride(
                        ticker, ind, spy_ind
                    )

                if not signal and strategy_name in (
                    'BREAKOUT', 'ALL'
                ):
                    signal = breakout_confirmation(
                        ticker, ind, spy_ind
                    )

                if not signal and strategy_name in (
                    'RS_TREND', 'ALL'
                ):
                    signal = relative_strength_trend(
                        ticker, ind, spy_ind
                    )

                if signal and signal.score >= 60:
                    entry_price = price * (
                        1 + SLIPPAGE
                    )
                    stop = entry_price * (
                        1 - self.stop_pct
                    )

                    risk_per_share = (
                        entry_price - stop
                    )
                    risk_amount = (
                        capital * self.risk_pct
                    )
                    shares = min(
                        risk_amount / risk_per_share,
                        capital * 0.33 / entry_price
                    )

                    cost = shares * entry_price
                    if cost <= capital and shares > 0:
                        capital -= cost
                        position = {
                            'ticker': ticker,
                            'strategy': signal.strategy,
                            'date': date_str,
                            'entry': entry_price,
                            'stop': stop,
                            'target1': entry_price *
                                (1 + self.target1_pct),
                            'target2': entry_price *
                                (1 + self.target2_pct),
                            'shares': shares,
                            'partial_sold': False,
                            'bar_index': i,
                        }

            # Record equity
            pos_value = (
                position['shares'] * price
                if position else 0
            )
            equity_curve.append(
                capital + pos_value
            )

        from backend.backtest.metrics import (
            compute_metrics
        )
        return compute_metrics(
            ticker=ticker,
            strategy=strategy_name,
            trades=trades,
            equity_curve=equity_curve,
            initial_capital=self.initial_capital
        )
