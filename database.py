import sqlite3
import os
import logging

logger = logging.getLogger(__name__)

DB_PATH = os.path.expanduser('~/sentinel/data/sentinel.db')


class Database:
    def __init__(self):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        self._init_tables()
        self.seed_defaults()
        self.seed_holdings()

    def _connect(self):
        return sqlite3.connect(DB_PATH)

    def _init_tables(self):
        with self._connect() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS watchlist (
                id INTEGER PRIMARY KEY,
                ticker TEXT UNIQUE NOT NULL,
                ticker_type TEXT DEFAULT 'stock',
                sector TEXT DEFAULT 'unknown',
                notes TEXT,
                active INTEGER DEFAULT 1,
                added_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS etf_holdings (
                id INTEGER PRIMARY KEY,
                ticker TEXT UNIQUE NOT NULL,
                shares REAL DEFAULT 0,
                avg_cost REAL DEFAULT 0,
                account TEXT DEFAULT 'robinhood',
                notes TEXT,
                added_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS my_holdings (
                id INTEGER PRIMARY KEY,
                ticker TEXT NOT NULL,
                shares REAL NOT NULL,
                avg_cost REAL NOT NULL,
                account TEXT DEFAULT 'robinhood',
                active INTEGER DEFAULT 1,
                added_at TEXT,
                updated_at TEXT
            );
            """)
        logger.info("Database tables initialized")

    def seed_defaults(self):
        with self._connect() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM watchlist"
            ).fetchone()[0]

        if count > 0:
            return

        default_stocks = [
            ('NVDA', 'stock', 'ai_tech'),
            ('AAPL', 'stock', 'consumer_tech'),
            ('MSFT', 'stock', 'ai_tech'),
            ('CRWD', 'stock', 'cybersecurity'),
            ('ASML', 'stock', 'semiconductors'),
            ('PLTR', 'stock', 'software'),
            ('RKLB', 'stock', 'space'),
            ('HOOD', 'stock', 'fintech'),
            ('RDDT', 'stock', 'social_media'),
            ('META', 'stock', 'ai_tech'),
            ('GRAB', 'stock', 'fintech'),
            ('XEL', 'stock', 'utilities'),
            ('NBIS', 'stock', 'speculative'),
        ]

        for ticker, t_type, sector in default_stocks:
            self.add_to_watchlist(ticker, t_type, sector)

        default_etfs = [
            ('VOO', 0, 0),
            ('QQQ', 0, 0),
            ('SPY', 0, 0),
            ('GLD', 0, 0),
        ]

        for ticker, shares, cost in default_etfs:
            self.add_etf_holding(ticker, shares, cost)

        logger.info("Default watchlist seeded")

    # ── WATCHLIST ─────────────────────────

    def get_watchlist(self) -> list:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM watchlist
                WHERE active = 1
                ORDER BY ticker_type, ticker
            """)
            return [dict(r) for r in cursor]

    def add_to_watchlist(self, ticker: str,
                          ticker_type: str = 'stock',
                          sector: str = 'unknown',
                          notes: str = '') -> bool:
        try:
            with self._connect() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO watchlist
                    (ticker, ticker_type, sector, notes, active)
                    VALUES (?, ?, ?, ?, 1)
                """, (ticker.upper(), ticker_type, sector, notes))
            return True
        except Exception as e:
            logger.error(f"Add watchlist error: {e}")
            return False

    def remove_from_watchlist(self, ticker: str):
        with self._connect() as conn:
            conn.execute("""
                UPDATE watchlist SET active = 0
                WHERE ticker = ?
            """, (ticker.upper(),))

    # ── ETF HOLDINGS ──────────────────────

    def get_etf_holdings(self) -> list:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM etf_holdings
                ORDER BY ticker
            """)
            return [dict(r) for r in cursor]

    def add_etf_holding(self, ticker: str,
                         shares: float = 0,
                         avg_cost: float = 0,
                         account: str = 'robinhood'):
        with self._connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO etf_holdings
                (ticker, shares, avg_cost, account)
                VALUES (?, ?, ?, ?)
            """, (ticker.upper(), shares, avg_cost, account))

    def remove_etf_holding(self, ticker: str):
        with self._connect() as conn:
            conn.execute("""
                DELETE FROM etf_holdings WHERE ticker = ?
            """, (ticker.upper(),))

    # ── SWING POSITIONS ───────────────────

    def get_swing_positions(self) -> list:
        try:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT * FROM positions
                    WHERE status = 'open'
                    ORDER BY entry_date DESC
                """)
                return [dict(r) for r in cursor]
        except Exception:
            return []

    # ── MY HOLDINGS (Robinhood) ───────────

    def get_my_holdings(self) -> list:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM my_holdings
                WHERE active = 1
                ORDER BY ticker
            """)
            return [dict(r) for r in cursor]

    def add_holding(
        self,
        ticker: str,
        shares: float,
        avg_cost: float,
        account: str = 'robinhood',
    ) -> bool:
        try:
            with self._connect() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO my_holdings
                    (ticker, shares, avg_cost,
                     account, active, added_at)
                    VALUES (?,?,?,?,1,datetime('now'))
                """, (
                    ticker.upper(),
                    shares,
                    avg_cost,
                    account,
                ))
            return True
        except Exception as e:
            logger.error(f"Add holding error: {e}")
            return False

    def update_holding(
        self,
        ticker: str,
        shares: float,
        avg_cost: float,
    ):
        with self._connect() as conn:
            conn.execute("""
                UPDATE my_holdings
                SET shares = ?,
                    avg_cost = ?,
                    updated_at = datetime('now')
                WHERE ticker = ?
            """, (shares, avg_cost, ticker.upper()))

    def remove_holding(self, ticker: str):
        with self._connect() as conn:
            conn.execute("""
                UPDATE my_holdings
                SET active = 0
                WHERE ticker = ?
            """, (ticker.upper(),))

    def seed_holdings(self):
        with self._connect() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM my_holdings"
            ).fetchone()[0]
        if count > 0:
            return

        default_holdings = [
            ('NVDA',  0.155913, 230.00),
            ('AAPL',  0.022544, 279.00),
            ('GRAB',  14.97,    3.68),
            ('AGIX',  1.14,     44.04),
            ('XEL',   0.731633, 57.67),
            ('NBIS',  0.940778, 0.00),
            ('PENG',  2.07,     0.00),
        ]

        for ticker, shares, cost in default_holdings:
            self.add_holding(ticker, shares, cost)

        logger.info("Default holdings seeded")
