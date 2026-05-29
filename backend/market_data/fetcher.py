from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging
import os
import time

import pandas as pd
from dotenv import load_dotenv

load_dotenv(os.path.expanduser('~/sentinel/.env'))

logger = logging.getLogger(__name__)

# Simple in-memory cache
_cache: dict = {}
_cache_time: dict = {}
CACHE_TTL = 300  # 5 minutes

PERIOD_DAYS: Dict[str, int] = {
    '1y': 365,
    '6mo': 180,
    '3mo': 90,
    '1mo': 30,
    '5d': 5,
    '2d': 2,
}


@dataclass
class MarketData:
    ticker: str
    df: pd.DataFrame
    cached: bool = False

    @property
    def latest(self) -> dict:
        if self.df.empty:
            return {}
        row = self.df.iloc[-1]
        return {
            'ticker': self.ticker,
            'close': float(row['Close']),
            'open': float(row['Open']),
            'high': float(row['High']),
            'low': float(row['Low']),
            'volume': float(row['Volume']),
        }


def get_client():
    from alpaca.data.historical import StockHistoricalDataClient
    key = os.getenv('ALPACA_API_KEY', '')
    secret = os.getenv('ALPACA_SECRET_KEY', '')
    if not key or not secret:
        return None
    return StockHistoricalDataClient(key, secret)


def fetch(
    ticker: str,
    period: str = '1y',
) -> Optional[MarketData]:

    cache_key = f"{ticker}_{period}"
    now = time.time()

    if (cache_key in _cache and
            now - _cache_time.get(cache_key, 0) < CACHE_TTL):
        return MarketData(
            ticker=ticker,
            df=_cache[cache_key],
            cached=True,
        )

    try:
        client = get_client()
        if not client:
            logger.warning('Alpaca keys missing')
            return None

        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame
        from alpaca.data.enums import DataFeed

        days = PERIOD_DAYS.get(period, 365)
        start = datetime.now() - timedelta(days=days)

        request = StockBarsRequest(
            symbol_or_symbols=ticker,
            timeframe=TimeFrame.Day,
            start=start,
            end=datetime.now(),
            feed=DataFeed.IEX,
        )

        bars = client.get_stock_bars(request)
        df = bars.df

        if df is None or df.empty:
            logger.warning(f"No data for {ticker}")
            return None

        # Flatten multi-index returned by alpaca-py
        if isinstance(df.index, pd.MultiIndex):
            df = df.xs(ticker, level='symbol')

        df = df.rename(columns={
            'open': 'Open',
            'high': 'High',
            'low': 'Low',
            'close': 'Close',
            'volume': 'Volume',
        })

        if len(df) < 20:
            logger.warning(
                f"Insufficient data for {ticker}: {len(df)} bars"
            )
            return None

        _cache[cache_key] = df
        _cache_time[cache_key] = now

        logger.info(f"Fetched {ticker}: {len(df)} bars")
        return MarketData(ticker=ticker, df=df)

    except Exception as e:
        logger.error(f"Failed to fetch {ticker}: {e}")
        return None


def fetch_many(
    tickers: List[str],
    period: str = '1y',
) -> Dict[str, MarketData]:
    results = {}
    for ticker in tickers:
        data = fetch(ticker, period)
        if data:
            results[ticker] = data
    return results


def get_current_price(ticker: str) -> float:
    data = fetch(ticker, period='5d')
    if data and not data.df.empty:
        return float(data.df['Close'].iloc[-1])
    return 0.0
