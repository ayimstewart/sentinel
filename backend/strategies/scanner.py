from dataclasses import dataclass
from typing import Optional
import pandas as pd


@dataclass
class Signal:
    ticker: str
    action: str        # READY / WATCH / AVOID
    strategy: str      # which strategy fired
    confidence: float  # 0.0 to 1.0
    score: int         # 0 to 100
    entry: float
    stop: float
    target1: float
    target2: float
    reason: str
    rules_passed: dict


def calculate_indicators(df) -> Optional[dict]:
    if df is None or len(df) < 50:
        return None

    close = df['Close']
    high = df['High']
    low = df['Low']
    volume = df['Volume']

    ema9 = close.ewm(span=9, adjust=False).mean()
    ema21 = close.ewm(span=21, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    ema200 = close.ewm(span=200, adjust=False).mean()

    delta = close.diff()
    gain = delta.clip(lower=0).ewm(span=14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(span=14, adjust=False).mean()
    rsi = 100 - (100 / (1 + gain / loss))

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    atr = tr.ewm(span=14, adjust=False).mean()

    avg_vol = volume.rolling(20).mean()
    current = float(close.iloc[-1])

    return {
        'close': current,
        'ema9': float(ema9.iloc[-1]),
        'ema21': float(ema21.iloc[-1]),
        'ema50': float(ema50.iloc[-1]),
        'ema200': float(ema200.iloc[-1]),
        'rsi': float(rsi.iloc[-1]),
        'atr': float(atr.iloc[-1]),
        'atr_pct': float(atr.iloc[-1] / current * 100),
        'volume': float(volume.iloc[-1]),
        'avg_volume': float(avg_vol.iloc[-1]),
        'volume_ratio': (
            float(volume.iloc[-1] / avg_vol.iloc[-1])
            if float(avg_vol.iloc[-1]) > 0 else 0
        ),
        'resistance': float(high.rolling(20).max().iloc[-1]),
        'support': float(low.rolling(20).min().iloc[-1]),
        'high_20d': float(high.rolling(20).max().iloc[-1]),
        'low_20d': float(low.rolling(20).min().iloc[-1]),
    }


def _score_to_action(score: int) -> str:
    if score >= 80:
        return 'READY'
    if score >= 60:
        return 'WATCH'
    return 'AVOID'


def ema_trend_ride(
    ticker: str, ind: dict, spy_ind: Optional[dict]
) -> Optional[Signal]:
    price = ind['close']

    near_ema21 = (
        abs(price - ind['ema21']) / ind['ema21'] < 0.03
    )

    rules = {
        'above_ema50': price > ind['ema50'],
        'ema9_above_ema21': ind['ema9'] > ind['ema21'],
        'near_ema21': near_ema21,
        'rsi_reset': 40 <= ind['rsi'] <= 55,
        'volume_ok': ind['volume_ratio'] >= 0.8,
    }

    if not all(rules.values()):
        return None

    score = 0
    score += 30 if rules['above_ema50'] else 0
    score += 25 if rules['near_ema21'] else 0
    score += 25 if rules['rsi_reset'] else 0
    score += 20 if rules['volume_ok'] else 0

    entry = ind['ema21'] * 1.001
    stop = entry * 0.97

    return Signal(
        ticker=ticker,
        action=_score_to_action(score),
        strategy='EMA_RIDE',
        confidence=round(score / 100, 2),
        score=score,
        entry=round(entry, 2),
        stop=round(stop, 2),
        target1=round(entry * 1.08, 2),
        target2=round(entry * 1.15, 2),
        reason=(
            f"Price near EMA21 in uptrend. "
            f"RSI reset to {ind['rsi']:.0f}."
        ),
        rules_passed=rules,
    )


def breakout_confirmation(
    ticker: str, ind: dict, spy_ind: Optional[dict]
) -> Optional[Signal]:
    price = ind['close']

    range_pct = (
        (ind['high_20d'] - ind['low_20d']) / ind['low_20d']
        if ind['low_20d'] > 0 else 1.0
    )

    rules = {
        'tight_range': range_pct < 0.15,
        'breaking_out': price >= ind['resistance'] * 0.99,
        'volume_confirms': ind['volume_ratio'] >= 1.5,
        'above_ema21': price > ind['ema21'],
        'ema9_above_ema21': ind['ema9'] > ind['ema21'],
    }

    if not all(rules.values()):
        return None

    score = 0
    if range_pct < 0.08:
        score += 30
    elif range_pct < 0.12:
        score += 20
    if ind['volume_ratio'] >= 2.0:
        score += 35
    elif ind['volume_ratio'] >= 1.5:
        score += 20
    score += 20 if rules['breaking_out'] else 0
    score += 15 if rules['above_ema21'] else 0

    entry = ind['resistance']
    stop = entry * 0.97

    return Signal(
        ticker=ticker,
        action=_score_to_action(score),
        strategy='BREAKOUT',
        confidence=round(score / 100, 2),
        score=score,
        entry=round(entry, 2),
        stop=round(stop, 2),
        target1=round(entry * 1.08, 2),
        target2=round(entry * 1.15, 2),
        reason=(
            f"Breaking above {ind['resistance']:.2f} "
            f"on {ind['volume_ratio']:.1f}x volume."
        ),
        rules_passed=rules,
    )


def relative_strength_trend(
    ticker: str, ind: dict, spy_ind: Optional[dict]
) -> Optional[Signal]:
    if not spy_ind:
        return None

    rs = (
        (ind['close'] - ind['ema50']) / ind['ema50'] -
        (spy_ind['close'] - spy_ind['ema50']) / spy_ind['ema50']
    ) * 100

    rules = {
        'above_ema21': ind['close'] > ind['ema21'],
        'ema9_above_ema21': ind['ema9'] > ind['ema21'],
        'above_ema50': ind['close'] > ind['ema50'],
        'rsi_healthy': 40 <= ind['rsi'] <= 65,
        'rs_positive': rs > 0,
        'volume_ok': ind['volume_ratio'] >= 0.8,
    }

    if not all(rules.values()):
        return None

    score = 0
    if rs > 5:
        score += 30
    elif rs > 2:
        score += 20
    elif rs > 0:
        score += 10
    if 45 <= ind['rsi'] <= 55:
        score += 25
    elif 40 <= ind['rsi'] <= 65:
        score += 15
    if ind['volume_ratio'] >= 1.5:
        score += 20
    elif ind['volume_ratio'] >= 0.8:
        score += 10
    if ind['close'] > ind['ema200']:
        score += 20

    entry = ind['ema21'] * 1.001
    stop = entry * 0.97

    return Signal(
        ticker=ticker,
        action=_score_to_action(score),
        strategy='RS_TREND',
        confidence=round(score / 100, 2),
        score=score,
        entry=round(entry, 2),
        stop=round(stop, 2),
        target1=round(entry * 1.08, 2),
        target2=round(entry * 1.15, 2),
        reason=(
            f"Outperforming SPY by {rs:.1f}%. "
            f"RSI {ind['rsi']:.0f}."
        ),
        rules_passed=rules,
    )


def get_market_trend(spy_ind: Optional[dict]) -> str:
    if not spy_ind:
        return 'NEUTRAL'
    if (spy_ind['close'] > spy_ind['ema21'] and
            spy_ind['ema9'] > spy_ind['ema21']):
        return 'BULLISH'
    elif spy_ind['close'] < spy_ind['ema50']:
        return 'BEARISH'
    return 'NEUTRAL'


def scan(
    ticker: str,
    df: pd.DataFrame,
    spy_df: Optional[pd.DataFrame] = None,
) -> Optional[Signal]:
    ind = calculate_indicators(df)
    spy_ind = (
        calculate_indicators(spy_df)
        if spy_df is not None else None
    )

    if not ind:
        return None

    market = get_market_trend(spy_ind)

    if market == 'BEARISH':
        return None

    strategies = [
        ema_trend_ride(ticker, ind, spy_ind),
        breakout_confirmation(ticker, ind, spy_ind),
        relative_strength_trend(ticker, ind, spy_ind),
    ]

    results = [s for s in strategies if s]

    if not results:
        return None

    return max(results, key=lambda s: s.score)
