from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import pandas as pd
import numpy as np
import logging
from backend.configs.symbols import MY_ROBINHOOD_STOCKS

logger = logging.getLogger(__name__)

# ── EXPANDED ETF UNIVERSE ─────────────────────────────────
ETF_UNIVERSE = {
    'technology':    ['XLK', 'QQQ', 'SMH', 'SOXX'],
    'growth':        ['VUG', 'IWF', 'SCHG'],
    'cybersecurity': ['CIBR', 'HACK', 'BUG'],
    'healthcare':    ['XLV', 'IBB', 'ARKG'],
    'industrials':   ['XLI', 'ITA', 'XAR'],
    'energy':        ['XLE', 'XOP', 'AMLP'],
    'nuclear':       ['URA', 'NLR'],
    'utilities':     ['XLU', 'IDU'],
    'gold':          ['GLD', 'IAU', 'GDX'],
    'small_caps':    ['IWM', 'VBR', 'IJR'],
    'broad_market':  ['SPY', 'IVV', 'VOO'],
    'bonds':         ['TLT', 'AGG', 'BND'],
    'real_estate':   ['VNQ', 'IYR'],
    'consumer':      ['XLY', 'XLP'],
    'finance':       ['XLF', 'KRE'],
}

TRADEABLE: List[str] = [
    etf
    for sector, etfs in ETF_UNIVERSE.items()
    if sector != 'broad_market'
    for etf in etfs
]

MARKET_FILTERS: List[str] = ['SPY', 'QQQ', 'IWM']


@dataclass
class ETFRank:
    ticker: str
    sector: str
    composite_score: float
    trend_score: float
    rs_score: float
    volume_score: float
    momentum_score: float
    volatility_score: float
    rsi: float
    overbought: bool
    overbought_penalty: float
    action: str
    entry: float
    stop: float
    target1: float
    target2: float
    reason: str


def get_sector(ticker: str) -> str:
    for sector, etfs in ETF_UNIVERSE.items():
        if ticker in etfs:
            return sector
    return 'unknown'


def calculate_all_indicators(
    df: pd.DataFrame,
) -> Optional[Dict]:
    if df is None or len(df) < 50:
        return None

    close = df['Close']
    high = df['High']
    low = df['Low']
    volume = df['Volume']

    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    ema200 = close.ewm(span=200, adjust=False).mean()

    delta = close.diff()
    gain = delta.clip(lower=0).ewm(span=14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(span=14, adjust=False).mean()
    rsi = 100 - (100 / (1 + gain / loss))

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(span=14, adjust=False).mean()

    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std
    bb_pct_b = (close - bb_lower) / (bb_upper - bb_lower)

    avg_vol = volume.rolling(20).mean()

    roc5 = close.pct_change(5) * 100
    roc10 = close.pct_change(10) * 100
    roc20 = close.pct_change(20) * 100

    current = float(close.iloc[-1])

    return {
        'close': current,
        'ema20': float(ema20.iloc[-1]),
        'ema50': float(ema50.iloc[-1]),
        'ema200': float(ema200.iloc[-1]),
        'rsi': float(rsi.iloc[-1]),
        'atr': float(atr.iloc[-1]),
        'atr_pct': float(atr.iloc[-1] / current * 100),
        'volume': float(volume.iloc[-1]),
        'avg_volume': float(avg_vol.iloc[-1]),
        'volume_ratio': (
            float(volume.iloc[-2]) / float(avg_vol.iloc[-2])
            if float(avg_vol.iloc[-2]) > 0 else 0
        ),
        'bb_pct_b': float(bb_pct_b.iloc[-1]),
        'roc5': float(roc5.iloc[-1]),
        'roc10': float(roc10.iloc[-1]),
        'roc20': float(roc20.iloc[-1]),
        'pct_above_ema50': float(
            (current - float(ema50.iloc[-1])) /
            float(ema50.iloc[-1]) * 100
        ),
    }


def score_trend(ind: Dict) -> float:
    score = 0.0
    price = ind['close']

    if price > ind['ema20']:  score += 25
    if price > ind['ema50']:  score += 35
    if price > ind['ema200']: score += 40

    if ind['ema20'] > ind['ema50'] > ind['ema200']:
        score += 20  # bonus for perfect bullish stack

    return min(score, 100)


def score_relative_strength(
    ind: Dict, spy_ind: Dict
) -> float:
    if not spy_ind:
        return 50.0

    score = 0.0

    rs_1w = ind.get('roc5', 0) - spy_ind.get('roc5', 0)
    rs_2w = ind.get('roc10', 0) - spy_ind.get('roc10', 0)
    rs_1m = ind.get('roc20', 0) - spy_ind.get('roc20', 0)

    if rs_1w > 2:   score += 35
    elif rs_1w > 0: score += 20
    elif rs_1w > -1: score += 10

    if rs_1m > 5:   score += 35
    elif rs_1m > 2: score += 20
    elif rs_1m > 0: score += 10

    if rs_2w > 0:   score += 30

    return min(score, 100)


def score_volume(ind: Dict) -> float:
    vol_ratio = ind.get('volume_ratio', 0)

    if vol_ratio >= 2.0:   return 100
    elif vol_ratio >= 1.5: return 80
    elif vol_ratio >= 1.2: return 60
    elif vol_ratio >= 1.0: return 40
    elif vol_ratio >= 0.8: return 25
    else:                  return 10


def score_volatility(ind: Dict) -> float:
    atr_pct = ind.get('atr_pct', 0)

    if atr_pct < 0.5:   return 40
    elif atr_pct < 1.0: return 60
    elif atr_pct < 2.0: return 90
    elif atr_pct < 3.0: return 100
    elif atr_pct < 4.0: return 70
    elif atr_pct < 5.0: return 40
    else:               return 10


def score_momentum(ind: Dict) -> float:
    score = 0.0

    roc5 = ind.get('roc5', 0)
    roc10 = ind.get('roc10', 0)
    roc20 = ind.get('roc20', 0)

    if roc5 > 3:   score += 35
    elif roc5 > 1: score += 20
    elif roc5 > 0: score += 10

    if roc10 > 5:   score += 35
    elif roc10 > 2: score += 20
    elif roc10 > 0: score += 10

    if roc20 > 8:   score += 30
    elif roc20 > 4: score += 20
    elif roc20 > 0: score += 10

    return min(score, 100)


def check_overbought(ind: Dict) -> Tuple[bool, float, List[str]]:
    rsi = ind.get('rsi', 50)
    pct_above_50 = ind.get('pct_above_ema50', 0)
    bb_pct_b = ind.get('bb_pct_b', 0.5)

    penalty = 0.0
    reasons: List[str] = []

    if rsi > 75:
        penalty += 30
        reasons.append(f"RSI {rsi:.0f}")
    elif rsi > 70:
        penalty += 15
        reasons.append(f"RSI elevated {rsi:.0f}")

    if pct_above_50 > 15:
        penalty += 25
        reasons.append(f"{pct_above_50:.0f}% above EMA50")
    elif pct_above_50 > 10:
        penalty += 10

    if bb_pct_b > 1.0:
        penalty += 20
        reasons.append("BB overbought")
    elif bb_pct_b > 0.9:
        penalty += 10

    return penalty >= 30, penalty, reasons


def calculate_composite_score(
    trend: float,
    rs: float,
    volume: float,
    volatility: float,
    momentum: float,
    overbought_penalty: float,
) -> float:
    raw = (
        trend    * 0.25 +
        rs       * 0.30 +
        volume   * 0.15 +
        volatility * 0.10 +
        momentum * 0.20
    )
    penalized = raw * (1 - overbought_penalty / 100)
    return round(max(penalized, 0), 1)


def get_action(score: float, overbought: bool) -> str:
    if overbought:      return 'AVOID'
    if score >= 75:     return 'READY'
    elif score >= 55:   return 'WATCH'
    return 'AVOID'


def rank_etfs(
    data_map: Dict,
    spy_ind: Optional[Dict],
) -> List[ETFRank]:
    ranks = []

    for ticker, data in data_map.items():
        if data is None:
            continue
        try:
            ind = calculate_all_indicators(data.df)
            if not ind:
                continue

            trend      = score_trend(ind)
            rs         = score_relative_strength(ind, spy_ind)
            volume     = score_volume(ind)
            volatility = score_volatility(ind)
            momentum   = score_momentum(ind)

            is_ob, penalty, ob_reasons = check_overbought(ind)

            composite = calculate_composite_score(
                trend, rs, volume, volatility, momentum, penalty
            )
            action = get_action(composite, is_ob)

            entry = round(ind['close'], 2)
            stop  = round(entry * 0.97, 2)
            t1    = round(entry * 1.08, 2)
            t2    = round(entry * 1.15, 2)

            reason_parts = []
            if ind['close'] > ind['ema50']:
                reason_parts.append('above EMA50')
            if rs > 60:
                reason_parts.append('strong RS')
            if ind['volume_ratio'] > 1.2:
                reason_parts.append('vol surge')
            if ob_reasons:
                reason_parts.append(
                    f"OVERBOUGHT: {', '.join(ob_reasons)}"
                )

            ranks.append(ETFRank(
                ticker=ticker,
                sector=get_sector(ticker),
                composite_score=composite,
                trend_score=trend,
                rs_score=rs,
                volume_score=volume,
                momentum_score=momentum,
                volatility_score=volatility,
                rsi=ind['rsi'],
                overbought=is_ob,
                overbought_penalty=penalty,
                action=action,
                entry=entry,
                stop=stop,
                target1=t1,
                target2=t2,
                reason=', '.join(reason_parts) or 'No strong signals',
            ))

        except Exception as e:
            logger.error(f"Ranking error {ticker}: {e}")

    ranks.sort(key=lambda x: x.composite_score, reverse=True)
    return ranks


def get_top3_diverse(ranks: List[ETFRank]) -> List[ETFRank]:
    top3: List[ETFRank] = []
    used_sectors: set = set()

    for rank in ranks:
        if rank.action == 'AVOID':
            continue
        if rank.sector in used_sectors:
            continue
        if len(top3) >= 3:
            break
        top3.append(rank)
        used_sectors.add(rank.sector)

    return top3


def run_ranking(fetcher_func) -> Tuple[List[ETFRank], List[ETFRank]]:
    all_tickers = list(dict.fromkeys(
        MY_ROBINHOOD_STOCKS + TRADEABLE
    ))
    logger.info(f"Ranking {len(all_tickers)} tickers...")

    spy_data = fetcher_func('SPY', '1y')
    spy_ind = (
        calculate_all_indicators(spy_data.df)
        if spy_data else None
    )

    data_map: Dict = {}
    for ticker in all_tickers:
        try:
            data = fetcher_func(ticker, '1y')
            if data:
                data_map[ticker] = data
        except Exception as e:
            logger.warning(f"Failed to fetch {ticker}: {e}")

    logger.info(f"Fetched {len(data_map)}/{len(all_tickers)} tickers")

    all_ranks = rank_etfs(data_map, spy_ind)
    top3 = get_top3_diverse(all_ranks)

    logger.info(f"Top 3 picks: {[r.ticker for r in top3]}")

    return all_ranks, top3
