import time
import logging
import schedule
from datetime import datetime

from backend.market_data.fetcher import fetch
from backend.strategies.scanner import scan
from backend.risk.engine import evaluate, Portfolio
from backend.portfolio.tracker import PortfolioTracker
from backend.execution.broker import (
    is_market_open,
    get_portfolio_value,
)
from backend.journal.logger import Journal
from backend.configs.symbols import TRADEABLE_ETFS

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
)
logger = logging.getLogger(__name__)

tracker = PortfolioTracker()
journal = Journal()


def run_scan():
    logger.info("=" * 40)
    logger.info("Starting ETF scan...")
    logger.info(f"ETFs: {TRADEABLE_ETFS}")

    if not is_market_open():
        logger.info("Market closed — skipping scan")
        journal.log_event('SCAN_SKIPPED', 'Market closed')
        return []

    spy_data = fetch('SPY', period='1y')
    if not spy_data:
        logger.error("Cannot fetch SPY data")
        return []

    portfolio_value = get_portfolio_value()
    open_positions = tracker.get_open_positions()

    logger.info(
        f"Portfolio: ${portfolio_value:.2f} | "
        f"Positions: {len(open_positions)}/3"
    )

    signals_found = []

    for ticker in TRADEABLE_ETFS:
        try:
            logger.info(f"Scanning {ticker}...")

            data = fetch(ticker, period='1y')
            if not data:
                journal.log_rejection(
                    ticker, 'No market data', 'market_data'
                )
                continue

            signal = scan(ticker, data.df, spy_data.df)

            if not signal:
                journal.log_rejection(
                    ticker, 'No strategy triggered', 'strategy'
                )
                logger.info(f"  {ticker}: no setup")
                continue

            logger.info(
                f"  {ticker}: {signal.action} "
                f"score={signal.score} "
                f"strategy={signal.strategy}"
            )

            portfolio = Portfolio(
                positions=open_positions,
                portfolio_value=portfolio_value,
                cash=portfolio_value,
                daily_pnl=0.0,
            )

            risk = evaluate(signal, portfolio)

            if not risk.allowed:
                journal.log_rejection(
                    ticker, risk.reason, 'risk'
                )
                logger.info(
                    f"  {ticker}: BLOCKED — {risk.reason}"
                )
                continue

            signal_id = journal.log_signal(
                ticker=ticker,
                strategy=signal.strategy,
                action=signal.action,
                score=signal.score,
                confidence=signal.confidence,
                entry=signal.entry,
                stop=signal.stop,
                target1=signal.target1,
                target2=signal.target2,
                reason=signal.reason,
                market_trend=signal.rules_passed.get(
                    'market', ''
                ),
            )

            signals_found.append({
                'signal_id': signal_id,
                'ticker': ticker,
                'strategy': signal.strategy,
                'action': signal.action,
                'score': signal.score,
                'entry': signal.entry,
                'stop': signal.stop,
                'target1': signal.target1,
                'target2': signal.target2,
                'shares': risk.shares,
                'cost': risk.position_value,
                'reason': signal.reason,
            })

            logger.info(
                f"  {ticker}: SIGNAL — "
                f"{signal.action} "
                f"entry=${signal.entry:.2f} "
                f"shares={risk.shares}"
            )

            time.sleep(2)

        except Exception as e:
            logger.error(f"Error scanning {ticker}: {e}")
            continue

    logger.info(
        f"Scan complete — {len(signals_found)} signals found"
    )
    logger.info("=" * 40)

    return signals_found


def run_bot():
    logger.info("SENTINEL starting...")
    logger.info(f"ETF universe: {TRADEABLE_ETFS}")

    journal.log_event('BOT_START', 'Sentinel started')

    run_scan()

    schedule.every(45).minutes.do(run_scan)

    logger.info("Scanning every 45 minutes")

    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == 'scan':
            results = run_scan()
            if results:
                print(f"\nSignals found: {len(results)}")
                for s in results:
                    print(
                        f"  {s['ticker']} "
                        f"{s['action']} "
                        f"score={s['score']}"
                    )
            else:
                print("No signals found")

        elif sys.argv[1] == 'status':
            positions = tracker.get_open_positions()
            stats = journal.get_stats()
            print(f"Open positions: {len(positions)}")
            print(f"Total trades:   {stats['total_trades']}")
            print(f"Win rate:       {stats['win_rate']}%")
            print(f"Total PnL:      ${stats['total_pnl']}")

    else:
        run_bot()
