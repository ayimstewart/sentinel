import sqlite3
import os
import json
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = os.path.expanduser(
    '~/sentinel/data/sentinel.db'
)


class Journal:
    def __init__(self):
        os.makedirs(
            os.path.dirname(DB_PATH),
            exist_ok=True,
        )
        self._init_tables()

    def _connect(self):
        return sqlite3.connect(DB_PATH)

    def _init_tables(self):
        with self._connect() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY,
                ticker TEXT NOT NULL,
                strategy TEXT NOT NULL,
                action TEXT NOT NULL,
                score INTEGER,
                confidence REAL,
                entry REAL,
                stop REAL,
                target1 REAL,
                target2 REAL,
                reason TEXT,
                market_trend TEXT,
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY,
                ticker TEXT NOT NULL,
                strategy TEXT NOT NULL,
                side TEXT NOT NULL,
                shares REAL,
                entry_price REAL,
                exit_price REAL,
                stop REAL,
                target1 REAL,
                target2 REAL,
                pnl REAL,
                pnl_pct REAL,
                entry_date TEXT,
                exit_date TEXT,
                exit_reason TEXT,
                hold_days INTEGER,
                approved_by TEXT DEFAULT 'human'
            );

            CREATE TABLE IF NOT EXISTS rejections (
                id INTEGER PRIMARY KEY,
                ticker TEXT NOT NULL,
                reason TEXT NOT NULL,
                module TEXT NOT NULL,
                details TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY,
                event_type TEXT NOT NULL,
                ticker TEXT,
                message TEXT NOT NULL,
                data TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            """)
        logger.info("Journal DB initialized")

    # ── SIGNALS ──────────────────────────

    def log_signal(
        self,
        ticker: str,
        strategy: str,
        action: str,
        score: int,
        confidence: float,
        entry: float,
        stop: float,
        target1: float,
        target2: float,
        reason: str,
        market_trend: str = '',
    ) -> int:
        with self._connect() as conn:
            cursor = conn.execute("""
                INSERT INTO signals
                (ticker, strategy, action, score,
                 confidence, entry, stop, target1,
                 target2, reason, market_trend)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (
                ticker, strategy, action, score,
                confidence, entry, stop, target1,
                target2, reason, market_trend,
            ))
            signal_id = cursor.lastrowid

        logger.info(
            f"Signal logged: {ticker} "
            f"{action} score={score}"
        )
        return signal_id

    def approve_signal(self, signal_id: int):
        with self._connect() as conn:
            conn.execute("""
                UPDATE signals SET status = 'approved'
                WHERE id = ?
            """, (signal_id,))
        logger.info(f"Signal {signal_id} approved")

    def skip_signal(
        self, signal_id: int, reason: str = ''
    ):
        with self._connect() as conn:
            conn.execute("""
                UPDATE signals SET status = 'skipped'
                WHERE id = ?
            """, (signal_id,))
        logger.info(f"Signal {signal_id} skipped")

    def get_todays_signals(self) -> list:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM signals
                WHERE date(created_at) = date('now')
                ORDER BY score DESC
            """)
            return [dict(r) for r in cursor]

    # ── TRADES ───────────────────────────

    def log_trade_open(
        self,
        ticker: str,
        strategy: str,
        shares: float,
        entry_price: float,
        stop: float,
        target1: float,
        target2: float,
        approved_by: str = 'human',
    ) -> int:
        with self._connect() as conn:
            cursor = conn.execute("""
                INSERT INTO trades
                (ticker, strategy, side, shares,
                 entry_price, stop, target1, target2,
                 entry_date, approved_by)
                VALUES (?,?,'buy',?,?,?,?,?,?,?)
            """, (
                ticker, strategy, shares, entry_price,
                stop, target1, target2,
                datetime.now().isoformat(),
                approved_by,
            ))
            trade_id = cursor.lastrowid

        logger.info(
            f"Trade opened: {ticker} "
            f"{shares} @ ${entry_price}"
        )
        return trade_id

    def log_trade_close(
        self,
        ticker: str,
        exit_price: float,
        exit_reason: str,
    ) -> Optional[dict]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row

            cursor = conn.execute("""
                SELECT * FROM trades
                WHERE ticker = ?
                AND exit_date IS NULL
                ORDER BY entry_date DESC
                LIMIT 1
            """, (ticker,))

            row = cursor.fetchone()
            if not row:
                logger.warning(
                    f"No open trade for {ticker}"
                )
                return None

            trade = dict(row)
            pnl = (
                exit_price - trade['entry_price']
            ) * trade['shares']
            pnl_pct = (
                (exit_price - trade['entry_price'])
                / trade['entry_price'] * 100
            )
            entry_dt = datetime.fromisoformat(
                trade['entry_date']
            )
            hold_days = (datetime.now() - entry_dt).days

            conn.execute("""
                UPDATE trades
                SET exit_price = ?,
                    exit_date = ?,
                    exit_reason = ?,
                    pnl = ?,
                    pnl_pct = ?,
                    hold_days = ?
                WHERE id = ?
            """, (
                exit_price,
                datetime.now().isoformat(),
                exit_reason,
                round(pnl, 2),
                round(pnl_pct, 2),
                hold_days,
                trade['id'],
            ))

            result = {
                **trade,
                'exit_price': exit_price,
                'exit_reason': exit_reason,
                'pnl': round(pnl, 2),
                'pnl_pct': round(pnl_pct, 2),
                'hold_days': hold_days,
            }

            logger.info(
                f"Trade closed: {ticker} "
                f"${pnl:+.2f} ({pnl_pct:+.1f}%)"
            )
            return result

    def get_all_trades(self) -> list:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM trades
                ORDER BY entry_date DESC
            """)
            return [dict(r) for r in cursor]

    def get_closed_trades(self) -> list:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM trades
                WHERE exit_date IS NOT NULL
                ORDER BY exit_date DESC
            """)
            return [dict(r) for r in cursor]

    # ── REJECTIONS ───────────────────────

    def log_rejection(
        self,
        ticker: str,
        reason: str,
        module: str,
        details: dict = None,
    ):
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO rejections
                (ticker, reason, module, details)
                VALUES (?,?,?,?)
            """, (
                ticker,
                reason,
                module,
                json.dumps(details or {}),
            ))
        logger.info(
            f"Rejected {ticker} [{module}]: {reason}"
        )

    def get_todays_rejections(self) -> list:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM rejections
                WHERE date(created_at) = date('now')
                ORDER BY created_at DESC
            """)
            return [dict(r) for r in cursor]

    # ── EVENTS ───────────────────────────

    def log_event(
        self,
        event_type: str,
        message: str,
        ticker: str = '',
        data: dict = None,
    ):
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO events
                (event_type, ticker, message, data)
                VALUES (?,?,?,?)
            """, (
                event_type,
                ticker,
                message,
                json.dumps(data or {}),
            ))

    # ── STATS ────────────────────────────

    def get_stats(self) -> dict:
        trades = self.get_closed_trades()

        if not trades:
            return {
                'total_trades': 0,
                'wins': 0,
                'losses': 0,
                'win_rate': 0.0,
                'total_pnl': 0.0,
                'profit_factor': 0.0,
                'avg_hold_days': 0.0,
                'best_trade': 0.0,
                'worst_trade': 0.0,
            }

        pnls = [
            t['pnl'] for t in trades
            if t.get('pnl') is not None
        ]

        if not pnls:
            return {'total_trades': 0}

        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        hold_days = [
            t.get('hold_days', 0) for t in trades
        ]

        gross_profit = sum(wins) if wins else 0
        gross_loss = abs(sum(losses)) if losses else 1

        return {
            'total_trades': len(pnls),
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': round(
                len(wins) / len(pnls) * 100, 1
            ),
            'total_pnl': round(sum(pnls), 2),
            'profit_factor': round(
                gross_profit / gross_loss, 2
            ),
            'avg_hold_days': (
                round(sum(hold_days) / len(hold_days), 1)
                if hold_days else 0
            ),
            'best_trade': round(max(pnls), 2),
            'worst_trade': round(min(pnls), 2),
        }

    def get_strategy_breakdown(self) -> dict:
        trades = self.get_closed_trades()
        breakdown = {}

        for t in trades:
            strat = t.get('strategy', 'unknown')
            if strat not in breakdown:
                breakdown[strat] = {
                    'trades': 0,
                    'wins': 0,
                    'total_pnl': 0.0,
                }

            pnl = t.get('pnl', 0) or 0
            breakdown[strat]['trades'] += 1
            breakdown[strat]['total_pnl'] += pnl
            if pnl > 0:
                breakdown[strat]['wins'] += 1

        for strat, data in breakdown.items():
            if data['trades'] > 0:
                data['win_rate'] = round(
                    data['wins'] / data['trades'] * 100, 1
                )

        return breakdown
