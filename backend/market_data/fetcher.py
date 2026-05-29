from dataclasses import dataclass
import pandas as pd
import yfinance as yf
import logging
import time
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Simple in-memory cache
_cache: dict = {}
_cache_time: dict = {}
CACHE_TTL = 300  # 5 minutes

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

def fetch(
    ticker: str,
    period: str = '1y'
) -> Optional[MarketData]:

    cache_key = f"{ticker}_{period}"
    now = time.time()

    # Return cached if fresh
    if (cache_key in _cache and
            now - _cache_time.get(cache_key, 0)
            < CACHE_TTL):
        return MarketData(
            ticker=ticker,
            df=_cache[cache_key],
            cached=True
        )

    try:
        df = yf.Ticker(ticker).history(
            period=period
        )

        if df is None or df.empty:
            logger.warning(
                f"No data returned for {ticker}"
            )
            return None

        if len(df) < 20:
            logger.warning(
                f"Insufficient data for {ticker}: "
                f"{len(df)} bars"
            )
            return None

        # Clean data
        df = df.dropna()
        df.index = pd.to_datetime(df.index)

        # Cache it
        _cache[cache_key] = df
        _cache_time[cache_key] = now

        logger.info(
            f"Fetched {ticker}: {len(df)} bars"
        )
        return MarketData(ticker=ticker, df=df)

    except Exception as e:
        logger.error(
            f"Failed to fetch {ticker}: {e}"
        )
        return None

def fetch_many(
    tickers: List[str],
    period: str = '1y'
) -> Dict[str, MarketData]:
    results = {}
    for ticker in tickers:
        data = fetch(ticker, period)
        if data:
            results[ticker] = data
    return results

def get_current_price(ticker: str) -> float:
    data = fetch(ticker, period='5d')
    if data:
        return data.latest.get('close', 0.0)
    return 0.0
