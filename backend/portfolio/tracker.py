import sqlite3
import os
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = os.path.expanduser(
    '~/sentinel/data/sentinel.db'
)


@dataclass
class Position:
    ticker: str
    shares: float
    entry_price: float
    stop_price: float
    target1: float
    target2: float
    strategy: str
    entry_date: str
    current_price: float = 0.0

    @property
    def pnl(self) -> float:
        if self.current_price <= 0:
            return 0.0
        return (
            self.current_price - self.entry_price
        ) * self.shares

    @property
    def pnl_pct(self) -> float:
        if self.entry_price <= 0:
            return 0.0
        return (
            (self.current_price - self.entry_price)
            / self.entry_price * 100
        )

    @property
    def cost_basis(self) -> float:
        return self.shares * self.entry_price

    @property
    def current_value(self) -> float:
        return self.shares * self.current_price


@dataclass
class PortfolioSnapshot:
    positions: list
    total_value: float
    total_cost: float
    total_pnl: float
    total_pnl_pct: float
    cash: float
    positions_used: int
    positions_max: int = 3


class PortfolioTracker:
    def __init__(self):
        os.makedirs(
            os.path.dirname(DB_PATH),
            exist_ok=True,
        )
        self._init_db()

    def _connect(self):
        return sqlite3.connect(DB_PATH)

    def _init_db(self):
        with self._connect() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY,
                ticker TEXT NOT NULL,
                shares REAL NOT NULL,
                entry_price REAL NOT NULL,
                stop_price REAL NOT NULL,
                target1 REAL NOT NULL,
                target2 REAL NOT NULL,
                strategy TEXT NOT NULL,
                status TEXT DEFAULT 'open',
                entry_date TEXT NOT NULL,
                exit_date TEXT,
                exit_price REAL,
                exit_reason TEXT,
                notes TEXT
            );
            """)
        logger.info("Portfolio DB initialized")

    def open_position(
        self,
        ticker: str,
        shares: float,
        entry_price: float,
        stop_price: float,
        target1: float,
        target2: float,
        strategy: str,
        notes: str = '',
    ) -> bool:
        try:
            with self._connect() as conn:
                conn.execute("""
                    INSERT INTO positions
                    (ticker, shares, entry_price,
                     stop_price, target1, target2,
                     strategy, status, entry_date,
                     notes)
                    VALUES (?,?,?,?,?,?,?,'open',?,?)
                """, (
                    ticker, shares, entry_price,
                    stop_price, target1, target2,
                    strategy,
                    datetime.now().isoformat(),
                    notes,
                ))
            logger.info(
                f"Opened position: {ticker} "
                f"{shares} shares @ ${entry_price}"
            )
            return True
        except Exception as e:
            logger.error(
                f"Failed to open position: {e}"
            )
            return False

    def close_position(
        self,
        ticker: str,
        exit_price: float,
        reason: str = 'manual',
    ) -> Optional[dict]:
        try:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row

                cursor = conn.execute("""
                    SELECT * FROM positions
                    WHERE ticker = ?
                    AND status = 'open'
                    ORDER BY entry_date DESC
                    LIMIT 1
                """, (ticker,))

                row = cursor.fetchone()
                if not row:
                    logger.warning(
                        f"No open position for {ticker}"
                    )
                    return None

                pos = dict(row)
                pnl = (
                    exit_price - pos['entry_price']
                ) * pos['shares']
                pnl_pct = (
                    (exit_price - pos['entry_price'])
                    / pos['entry_price'] * 100
                )

                conn.execute("""
                    UPDATE positions
                    SET status = 'closed',
                        exit_date = ?,
                        exit_price = ?,
                        exit_reason = ?
                    WHERE id = ?
                """, (
                    datetime.now().isoformat(),
                    exit_price,
                    reason,
                    pos['id'],
                ))

                result = {
                    'ticker': ticker,
                    'entry': pos['entry_price'],
                    'exit': exit_price,
                    'shares': pos['shares'],
                    'pnl': round(pnl, 2),
                    'pnl_pct': round(pnl_pct, 2),
                    'strategy': pos['strategy'],
                    'reason': reason,
                }

                logger.info(
                    f"Closed {ticker}: "
                    f"${pnl:+.2f} ({pnl_pct:+.1f}%)"
                )
                return result

        except Exception as e:
            logger.error(
                f"Failed to close position: {e}"
            )
            return None

    def get_open_positions(self) -> list:
        try:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT * FROM positions
                    WHERE status = 'open'
                    ORDER BY entry_date DESC
                """)
                return [dict(r) for r in cursor]
        except Exception as e:
            logger.error(f"DB error: {e}")
            return []

    def get_snapshot(
        self,
        current_prices: dict = None,
    ) -> PortfolioSnapshot:
        positions = self.get_open_positions()
        current_prices = current_prices or {}

        position_objects = []
        total_cost = 0.0
        total_value = 0.0

        for p in positions:
            current = current_prices.get(
                p['ticker'], p['entry_price']
            )
            pos = Position(
                ticker=p['ticker'],
                shares=p['shares'],
                entry_price=p['entry_price'],
                stop_price=p['stop_price'],
                target1=p['target1'],
                target2=p['target2'],
                strategy=p['strategy'],
                entry_date=p['entry_date'],
                current_price=current,
            )
            position_objects.append(pos)
            total_cost += pos.cost_basis
            total_value += pos.current_value

        total_pnl = total_value - total_cost
        total_pnl_pct = (
            (total_pnl / total_cost * 100)
            if total_cost > 0 else 0.0
        )

        budget = float(os.getenv('SWING_BUDGET', '300'))
        cash = max(budget - total_cost, 0)

        return PortfolioSnapshot(
            positions=position_objects,
            total_value=round(total_value, 2),
            total_cost=round(total_cost, 2),
            total_pnl=round(total_pnl, 2),
            total_pnl_pct=round(total_pnl_pct, 2),
            cash=round(cash, 2),
            positions_used=len(positions),
        )

    def get_closed_trades(self) -> list:
        try:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT * FROM positions
                    WHERE status = 'closed'
                    ORDER BY exit_date DESC
                """)
                return [dict(r) for r in cursor]
        except Exception as e:
            logger.error(f"DB error: {e}")
            return []

    def get_stats(self) -> dict:
        trades = self.get_closed_trades()

        if not trades:
            return {
                'total_trades': 0,
                'wins': 0,
                'losses': 0,
                'win_rate': 0.0,
                'total_pnl': 0.0,
                'avg_win': 0.0,
                'avg_loss': 0.0,
                'profit_factor': 0.0,
            }

        pnls = []
        for t in trades:
            if t.get('exit_price') and t.get('entry_price'):
                pnl = (
                    t['exit_price'] - t['entry_price']
                ) * t['shares']
                pnls.append(pnl)

        if not pnls:
            return {'total_trades': 0}

        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        win_rate = len(wins) / len(pnls) * 100

        gross_profit = sum(wins) if wins else 0
        gross_loss = abs(sum(losses)) if losses else 1
        profit_factor = gross_profit / gross_loss

        return {
            'total_trades': len(pnls),
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': round(win_rate, 1),
            'total_pnl': round(sum(pnls), 2),
            'avg_win': (
                round(sum(wins) / len(wins), 2)
                if wins else 0
            ),
            'avg_loss': (
                round(abs(sum(losses) / len(losses)), 2)
                if losses else 0
            ),
            'profit_factor': round(profit_factor, 2),
        }
