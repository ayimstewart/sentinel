import logging
import time
from typing import List
from dataclasses import dataclass

logger = logging.getLogger(__name__)

DISCOVERY_UNIVERSE = [
    # Mega cap tech
    'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'META',
    'AMZN', 'TSLA', 'AVGO', 'ORCL', 'ADBE',
    # Semiconductors
    'AMD', 'ASML', 'QCOM', 'INTC', 'MU',
    'AMAT', 'LRCX', 'KLAC', 'MRVL', 'SMCI',
    # Software/Cloud
    'NOW', 'CRM', 'SNOW', 'MDB', 'DDOG',
    'PLTR', 'CRWD', 'ZS', 'PANW', 'FTNT',
    'NET', 'OKTA', 'HUBS', 'TEAM', 'WDAY',
    # Fintech
    'HOOD', 'SOFI', 'SQ', 'AFRM', 'COIN',
    'V', 'MA', 'PYPL', 'NU', 'SEZZLE',
    # Growth/Consumer
    'SHOP', 'MELI', 'SE', 'GRAB', 'BABA',
    'JD', 'PDD', 'UBER', 'LYFT', 'ABNB',
    # Biotech/Health
    'MRNA', 'BNTX', 'NVAX', 'RXRX',
    'CRSP', 'EDIT', 'BEAM', 'NTLA',
    # Space/Defense
    'RKLB', 'ASTS', 'LUNR', 'MNTS',
    'LMT', 'RTX', 'NOC', 'GD', 'KTOS',
    # Nuclear/Energy
    'OKLO', 'SMR', 'CEG', 'VST', 'NRG',
    'FSLR', 'ENPH', 'SEDG', 'BE',
    # Social/Media
    'RDDT', 'SNAP', 'PINS', 'SPOT',
    'NFLX', 'DIS', 'WBD', 'PARA',
    # Small cap momentum
    'IONQ', 'QUBT', 'RGTI', 'QBTS',
    'ACHR', 'JOBY', 'LILM', 'EVTL',
    # ETFs (as swing opportunities)
    'SMH', 'XLK', 'CIBR', 'SOXX',
    'ARKK', 'ARKG', 'ARKF', 'ARKQ',
]

_SECTOR_MAP = {
    'NVDA': 'ai_tech', 'MSFT': 'ai_tech',
    'META': 'ai_tech', 'GOOGL': 'ai_tech',
    'PLTR': 'ai_tech', 'AAPL': 'consumer_tech',
    'AMZN': 'consumer_tech', 'TSLA': 'consumer_tech',
    'ASML': 'semiconductors', 'AMD': 'semiconductors',
    'QCOM': 'semiconductors', 'MU': 'semiconductors',
    'SMCI': 'semiconductors', 'CRWD': 'cybersecurity',
    'PANW': 'cybersecurity', 'ZS': 'cybersecurity',
    'FTNT': 'cybersecurity', 'NET': 'cybersecurity',
    'NOW': 'software', 'SNOW': 'software',
    'DDOG': 'software', 'MDB': 'software',
    'HOOD': 'fintech', 'COIN': 'fintech',
    'SOFI': 'fintech', 'RKLB': 'space',
    'ASTS': 'space', 'OKLO': 'nuclear',
    'SMR': 'nuclear', 'RDDT': 'social_media',
    'SNAP': 'social_media', 'MRNA': 'biotech',
    'GRAB': 'fintech', 'XEL': 'utilities',
    'IONQ': 'quantum',
}


@dataclass
class Discovery:
    ticker: str
    score: float
    reason: str
    sector: str
    rs_vs_spy: float
    momentum_5d: float
    momentum_20d: float
    volume_ratio: float
    rsi: float
    action: str


def discover_opportunities(
    fetch_func,
    min_score: float = 70.0,
    max_results: int = 10
) -> List[Discovery]:
    logger.info(
        f"Discovering from "
        f"{len(DISCOVERY_UNIVERSE)} stocks..."
    )

    spy_data = fetch_func('SPY', '1y')
    if not spy_data:
        return []

    from backend.strategies.scanner import (
        calculate_indicators
    )
    spy_ind = calculate_indicators(spy_data.df)
    if not spy_ind:
        return []

    discoveries = []

    for ticker in DISCOVERY_UNIVERSE:
        try:
            data = fetch_func(ticker, '1y')
            if not data or len(data.df) < 50:
                continue

            ind = calculate_indicators(data.df)
            if not ind:
                continue

            score = _score_discovery(ind, spy_ind)

            if score < min_score:
                continue

            rs = (
                (ind['close'] - ind['ema50']) /
                ind['ema50'] -
                (spy_ind['close'] -
                 spy_ind['ema50']) /
                spy_ind['ema50']
            ) * 100

            mom_5d = ind.get('roc5', 0)
            mom_20d = ind.get('roc20', 0)

            reason = _build_reason(ind, rs)
            sector = _guess_sector(ticker)
            action = (
                'READY' if score >= 80 else 'WATCH'
            )

            discoveries.append(Discovery(
                ticker=ticker,
                score=round(score, 1),
                reason=reason,
                sector=sector,
                rs_vs_spy=round(rs, 2),
                momentum_5d=round(mom_5d, 2),
                momentum_20d=round(mom_20d, 2),
                volume_ratio=round(
                    ind['volume_ratio'], 2
                ),
                rsi=round(ind['rsi'], 1),
                action=action,
            ))

            time.sleep(0.5)

        except Exception as e:
            logger.warning(
                f"Discovery skip {ticker}: {e}"
            )

    discoveries.sort(key=lambda x: x.score, reverse=True)

    logger.info(
        f"Found {len(discoveries)} opportunities"
    )
    return discoveries[:max_results]


def _score_discovery(ind, spy_ind) -> float:
    score = 0.0
    price = ind['close']

    # Trend (30 points)
    if price > ind['ema20']:
        score += 10
    if price > ind['ema50']:
        score += 15
    if price > ind['ema200']:
        score += 5

    # RS vs SPY (25 points)
    rs = (
        (price - ind['ema50']) / ind['ema50'] -
        (spy_ind['close'] - spy_ind['ema50']) /
        spy_ind['ema50']
    ) * 100
    if rs > 5:
        score += 25
    elif rs > 2:
        score += 15
    elif rs > 0:
        score += 8

    # Momentum (25 points)
    roc5 = ind.get('roc5', 0)
    roc20 = ind.get('roc20', 0)
    if roc5 > 3:
        score += 15
    elif roc5 > 1:
        score += 8
    if roc20 > 8:
        score += 10
    elif roc20 > 3:
        score += 5

    # Volume (15 points)
    vol = ind.get('volume_ratio', 0)
    if vol >= 1.5:
        score += 15
    elif vol >= 1.2:
        score += 10
    elif vol >= 1.0:
        score += 5

    # RSI filter (penalty)
    rsi = ind['rsi']
    if rsi > 75:
        score -= 20
    elif rsi > 70:
        score -= 10
    elif rsi < 40:
        score -= 15

    return max(score, 0)


def _build_reason(ind, rs) -> str:
    parts = []
    price = ind['close']

    if price > ind['ema50']:
        parts.append('above EMA50')
    if rs > 2:
        parts.append(f'beating SPY by {rs:.1f}%')
    if ind.get('volume_ratio', 0) > 1.3:
        parts.append('strong volume')
    if 45 <= ind['rsi'] <= 60:
        parts.append('RSI healthy')

    return (
        ', '.join(parts) if parts
        else 'momentum detected'
    )


def _guess_sector(ticker) -> str:
    return _SECTOR_MAP.get(ticker, 'other')


def auto_add_discoveries(
    fetch_func,
    db,
    min_score: float = 75.0
):
    discoveries = discover_opportunities(
        fetch_func, min_score
    )

    added = []
    for d in discoveries:
        watchlist = db.get_watchlist()
        existing = [w['ticker'] for w in watchlist]

        if d.ticker not in existing:
            db.add_to_watchlist(
                d.ticker,
                'stock',
                d.sector,
                f"Auto-discovered: {d.reason}"
            )
            added.append(d.ticker)
            logger.info(
                f"Auto-added: {d.ticker} "
                f"score={d.score}"
            )

    return added, discoveries
