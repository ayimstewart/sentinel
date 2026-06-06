from dataclasses import dataclass, field
from typing import Optional
import logging
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class Signal:
    ticker: str
    action: str        # BUY_ZONE / WATCH / TOO_HIGH
    strategy: str
    confidence: float  # 0.0 to 1.0
    score: int         # 0 to 100
    entry: float
    stop: float
    target1: float
    target2: float
    reason: str
    rules_passed: dict
    state: str = 'WATCH'
    entry_zone_low: float = 0.0
    entry_zone_high: float = 0.0
    rr_ratio: float = 0.0
    pct_above_ema21: float = 0.0
    rsi: float = 50.0
    rs_vs_spy: float = 0.0
    hold_days: int = 12
    atr_stop_mult: float = 1.5
    hold_plan: dict = field(default_factory=dict)


def calculate_indicators(df) -> Optional[dict]:
    if df is None or len(df) < 50:
        return None

    close = df['Close']
    high = df['High']
    low = df['Low']
    volume = df['Volume']

    ema9 = close.ewm(span=9, adjust=False).mean()
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema21 = close.ewm(span=21, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    ema200 = close.ewm(span=200, adjust=False).mean()

    delta = close.diff()
    gain = delta.clip(lower=0).ewm(
        span=14, adjust=False
    ).mean()
    loss = (-delta.clip(upper=0)).ewm(
        span=14, adjust=False
    ).mean()
    rsi = 100 - (100 / (1 + gain / loss))

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    atr = tr.ewm(span=14, adjust=False).mean()

    avg_vol = volume.rolling(20).mean()
    current = float(close.iloc[-1])

    roc5 = (
        (float(close.iloc[-1]) /
         float(close.iloc[-6]) - 1) * 100
        if len(close) >= 6 else 0.0
    )
    roc20 = (
        (float(close.iloc[-1]) /
         float(close.iloc[-21]) - 1) * 100
        if len(close) >= 21 else 0.0
    )

    return {
        'close': current,
        'ema9': float(ema9.iloc[-1]),
        'ema20': float(ema20.iloc[-1]),
        'ema21': float(ema21.iloc[-1]),
        'ema50': float(ema50.iloc[-1]),
        'ema200': float(ema200.iloc[-1]),
        'rsi': float(rsi.iloc[-1]),
        'atr': float(atr.iloc[-1]),
        'atr_pct': float(atr.iloc[-1] / current * 100),
        'volume': float(volume.iloc[-2]),
        'avg_volume': float(avg_vol.iloc[-2]),
        'volume_ratio': round(
            float(volume.iloc[-2]) /
            float(avg_vol.iloc[-2]), 2
        ) if float(avg_vol.iloc[-2]) > 0 else 0,
        'resistance': float(
            high.rolling(20).max().iloc[-1]
        ),
        'support': float(
            low.rolling(20).min().iloc[-1]
        ),
        'high_20d': float(
            high.rolling(20).max().iloc[-1]
        ),
        'low_20d': float(
            low.rolling(20).min().iloc[-1]
        ),
        'roc5': round(roc5, 2),
        'roc20': round(roc20, 2),
    }


def get_market_trend(spy_ind: Optional[dict]) -> str:
    if not spy_ind:
        return 'NEUTRAL'
    if (spy_ind['close'] > spy_ind['ema21'] and
            spy_ind['ema9'] > spy_ind['ema21']):
        return 'BULLISH'
    elif spy_ind['close'] < spy_ind['ema50']:
        return 'BEARISH'
    return 'NEUTRAL'


def _build_pullback_reason(
    state: str,
    pct_above: float,
    rsi: float,
    zone_low: float,
    zone_high: float,
) -> str:
    if state == 'BUY_ZONE':
        return (
            f"Price in buy zone "
            f"${zone_low:.2f}-${zone_high:.2f}. "
            f"RSI reset to {rsi:.0f}. "
            f"Good risk/reward entry."
        )
    elif state == 'WATCH':
        return (
            f"Price {pct_above:.1f}% above EMA21. "
            f"Wait for pullback to "
            f"${zone_low:.2f}-${zone_high:.2f}."
        )
    else:
        return (
            f"Price {pct_above:.1f}% above EMA21. "
            f"RSI {rsi:.0f}. Too extended. "
            f"Wait for 10-15% pullback."
        )


def check_earnings_safe(
    ticker: str,
    buffer_days: int = 7,
) -> bool:
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        cal = t.calendar

        if cal is None or cal.empty:
            return True

        from datetime import datetime
        today = datetime.now()

        for col in cal.columns:
            try:
                earnings_date = cal[col].iloc[0]
                if hasattr(earnings_date, 'date'):
                    days_away = abs(
                        (earnings_date - today).days
                    )
                    if days_away <= buffer_days:
                        return False
            except Exception:
                continue

        return True

    except Exception:
        return True


def pullback_strategy(
    ticker: str,
    ind: dict,
    spy_ind: Optional[dict],
) -> Optional[dict]:

    price = ind['close']
    ema21 = ind['ema21']
    ema50 = ind['ema50']
    ema200 = ind['ema200']
    rsi = ind['rsi']

    # Must be in uptrend: above EMA50 and EMA200
    if price < ema50 or price < ema200:
        return None

    # Market must be bullish
    if spy_ind:
        if spy_ind['close'] < spy_ind['ema50']:
            return None

    pct_above_ema21 = (price - ema21) / ema21 * 100
    pct_above_ema50 = (price - ema50) / ema50 * 100

    # Entry zone = EMA21 area +/- 2%
    entry_zone_low = ema21 * 0.98
    entry_zone_high = ema21 * 1.02

    # ATR-based stop
    atr = ind['atr']
    atr_pct = ind['atr_pct']

    if atr_pct > 4:
        atr_mult = 2.0
    elif atr_pct > 3:
        atr_mult = 1.75
    else:
        atr_mult = 1.5

    stop = round(
        entry_zone_high - (atr * atr_mult), 2
    )
    # Clamp stop: min 2% below entry, max 8% below
    min_stop = round(entry_zone_high * 0.98, 2)
    stop = min(stop, min_stop)
    max_stop = round(entry_zone_high * 0.92, 2)
    stop = max(stop, max_stop)

    # Hold days based on volatility
    if atr_pct >= 3.0:
        hold_days = 7
    elif atr_pct >= 2.0:
        hold_days = 10
    else:
        hold_days = 14

    target1 = round(ema21 * 1.10, 2)
    target2 = round(ema21 * 1.18, 2)

    rr_ratio = round(
        (target1 - entry_zone_high) /
        (entry_zone_high - stop), 2
    ) if (entry_zone_high - stop) > 0 else 0

    # Require at least 1.5:1 R/R
    if rr_ratio < 1.5:
        return None

    rs = 0
    if spy_ind:
        rs = (
            ind.get('roc20', 0) -
            spy_ind.get('roc20', 0)
        )

    # Determine state
    if entry_zone_low <= price <= entry_zone_high:
        rsi_reset = 40 <= rsi <= 58
        vol_dry = ind.get('volume_ratio', 1) < 1.0

        if rsi_reset and vol_dry:
            state = 'BUY_ZONE'
            confidence = 90
        elif rsi_reset:
            state = 'BUY_ZONE'
            confidence = 75
        else:
            state = 'WATCH'
            confidence = 60

    elif (price > entry_zone_high and
          pct_above_ema21 < 8):
        state = 'WATCH'
        confidence = 65

    elif pct_above_ema21 > 15 or rsi > 70:
        state = 'TOO_HIGH'
        confidence = 30

    else:
        state = 'WATCH'
        confidence = 55

    return {
        'ticker': ticker,
        'strategy': 'PULLBACK',
        'state': state,
        'action': state,
        'confidence': confidence,
        'score': confidence,
        'price': price,
        'entry_zone_low': round(entry_zone_low, 2),
        'entry_zone_high': round(entry_zone_high, 2),
        'entry': round(entry_zone_high, 2),
        'stop': stop,
        'target1': target1,
        'target2': target2,
        'rr_ratio': rr_ratio,
        'hold_days': hold_days,
        'atr_stop_mult': atr_mult,
        'pct_above_ema21': round(pct_above_ema21, 1),
        'pct_above_ema50': round(pct_above_ema50, 1),
        'rsi': round(rsi, 1),
        'rs_vs_spy': round(rs, 2),
        'reason': _build_pullback_reason(
            state, pct_above_ema21, rsi,
            entry_zone_low, entry_zone_high,
        ),
        'rules_passed': {
            'uptrend': True,
            'above_ema200': price > ema200,
            'rs_positive': rs > 0,
            'rr_ratio': rr_ratio,
        },
    }


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

    if not check_earnings_safe(ticker):
        logger.info(
            f"{ticker}: Skipped — "
            f"earnings within 7 days"
        )
        return None

    result = pullback_strategy(ticker, ind, spy_ind)

    if result is None:
        return None

    return Signal(
        ticker=result['ticker'],
        action=result['action'],
        strategy=result['strategy'],
        confidence=result['confidence'] / 100.0,
        score=result['score'],
        entry=result['entry'],
        stop=result['stop'],
        target1=result['target1'],
        target2=result['target2'],
        reason=result['reason'],
        rules_passed=result['rules_passed'],
        state=result['state'],
        entry_zone_low=result['entry_zone_low'],
        entry_zone_high=result['entry_zone_high'],
        rr_ratio=result['rr_ratio'],
        pct_above_ema21=result['pct_above_ema21'],
        rsi=result['rsi'],
        rs_vs_spy=result['rs_vs_spy'],
        hold_days=result['hold_days'],
        atr_stop_mult=result['atr_stop_mult'],
    )
