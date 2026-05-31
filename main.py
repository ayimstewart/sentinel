import os
import time
import logging
import schedule
from datetime import datetime

import pytz
import requests
from dotenv import load_dotenv

load_dotenv(os.path.expanduser('~/sentinel/.env'))

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

DASHBOARD_URL = 'http://129.158.37.181:8501'


# ── TELEGRAM ─────────────────────────────────────────────

def _send_telegram(message: str):
    token = os.getenv('TELEGRAM_BOT_TOKEN', '')
    chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
    if not token or not chat_id:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={'chat_id': chat_id, 'text': message},
            timeout=10,
        )
    except Exception as e:
        logger.error(f"Telegram error: {e}")


# ── MORNING BRIEF ─────────────────────────────────────────

def send_morning_brief():
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')

    if not token or not chat_id:
        logger.warning('Telegram not configured')
        return

    try:
        spy_data = fetch('SPY', '1y')
        qqq_data = fetch('QQQ', '5d')

        if spy_data and len(spy_data.df) >= 2:
            spy_close = float(spy_data.df['Close'].iloc[-1])
            spy_prev = float(spy_data.df['Close'].iloc[-2])
            spy_chg = (spy_close - spy_prev) / spy_prev * 100
        else:
            spy_chg = 0.0

        if qqq_data and len(qqq_data.df) >= 2:
            qqq_close = float(qqq_data.df['Close'].iloc[-1])
            qqq_prev = float(qqq_data.df['Close'].iloc[-2])
            qqq_chg = (qqq_close - qqq_prev) / qqq_prev * 100
        else:
            qqq_chg = 0.0

        market = '🟢 BULLISH' if spy_chg > 0 else '🔴 BEARISH'

        positions = tracker.get_open_positions()
        budget = float(os.getenv('SWING_BUDGET', '300'))
        signals = journal.get_todays_signals()

        est = pytz.timezone('US/Eastern')
        now = datetime.now(est)

        msg = (
            f"⚡ SENTINEL MORNING BRIEF\n"
            f"{now.strftime('%A %B %d')}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Market: {market}\n"
            f"SPY: {spy_chg:+.1f}% | QQQ: {qqq_chg:+.1f}%\n\n"
            f"Open positions: {len(positions)}/3\n"
            f"Budget: ${budget:.0f} available\n\n"
        )

        if signals:
            msg += f"📡 {len(signals)} setups found\n"
            for s in signals[:3]:
                action = s.get('action', '')
                ticker = s.get('ticker', '')
                score = s.get('score', 0)
                emoji = '🟢' if action == 'READY' else '🟡'
                msg += f"{emoji} {ticker} — {action} ({score}/100)\n"
            msg += "\nCheck dashboard to approve"
        else:
            msg += (
                "No setups today\n"
                "Market conditions not ideal\n"
                "Bot will alert when ready"
            )

        msg += f"\n\nDashboard: {DASHBOARD_URL}"

        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={'chat_id': chat_id, 'text': msg},
            timeout=10,
        )
        logger.info("Morning brief sent")

    except Exception as e:
        logger.error(f"Morning brief error: {e}")


# ── EXIT ALERTS ───────────────────────────────────────────

def check_exit_alerts():
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')

    positions = tracker.get_open_positions()
    if not positions:
        return

    for pos in positions:
        ticker = pos['ticker']
        entry = pos.get('entry_price', 0)
        stop = pos.get('stop_price', 0)
        target1 = pos.get('target1', 0)

        try:
            data = fetch(ticker, '5d')
            if not data:
                continue

            current = float(data.df['Close'].iloc[-1])
            pnl_pct = (
                (current - entry) / entry * 100
                if entry > 0 else 0
            )

            if current <= stop * 1.01:
                msg = (
                    f"🛑 STOP ALERT — {ticker}\n"
                    f"Price: ${current:.2f}\n"
                    f"Stop: ${stop:.2f}\n"
                    f"PnL: {pnl_pct:+.1f}%\n\n"
                    f"Consider selling on Robinhood"
                )
                if token and chat_id:
                    requests.post(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        json={'chat_id': chat_id, 'text': msg},
                        timeout=10,
                    )

            elif current >= target1 * 0.99:
                msg = (
                    f"🎯 TARGET HIT — {ticker}\n"
                    f"Price: ${current:.2f}\n"
                    f"Target: ${target1:.2f}\n"
                    f"PnL: {pnl_pct:+.1f}%\n\n"
                    f"Consider selling 50% on Robinhood"
                )
                if token and chat_id:
                    requests.post(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        json={'chat_id': chat_id, 'text': msg},
                        timeout=10,
                    )

        except Exception as e:
            logger.error(f"Exit check error {ticker}: {e}")


# ── WEEKLY REVIEW ─────────────────────────────────────────

def send_weekly_review():
    stats = journal.get_stats()
    positions = tracker.get_open_positions()

    msg = (
        f"📊 SENTINEL WEEKLY REVIEW\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"PERFORMANCE\n"
        f"Total trades: {stats.get('total_trades', 0)}\n"
        f"Win rate: {stats.get('win_rate', 0):.0f}%\n"
        f"Total PnL: ${stats.get('total_pnl', 0):+.2f}\n"
        f"Profit factor: {stats.get('profit_factor', 0):.2f}\n\n"
        f"POSITIONS\n"
        f"Open: {len(positions)}/3\n\n"
        f"GOAL\n"
        f"Car fund progress updating...\n\n"
        f"Have a great weekend! 🎯"
    )
    _send_telegram(msg)


# ── SCAN ──────────────────────────────────────────────────

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
                market_trend=signal.rules_passed.get('market', ''),
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


# ── BOT RUNNER ────────────────────────────────────────────

def run_bot():
    logger.info("SENTINEL starting...")
    logger.info(f"ETF universe: {TRADEABLE_ETFS}")

    journal.log_event('BOT_START', 'Sentinel started')

    _send_telegram(
        f"⚡ Sentinel started\n"
        f"Scanning every 45 minutes\n"
        f"Dashboard: {DASHBOARD_URL}"
    )

    run_scan()

    schedule.every().day.at("09:00").do(send_morning_brief)
    schedule.every(45).minutes.do(run_scan)
    schedule.every(30).minutes.do(check_exit_alerts)
    schedule.every().sunday.at("18:00").do(send_weekly_review)

    logger.info(
        "Schedule: scan 45min, morning brief 9am, "
        "exit checks 30min, weekly review Sun 6pm"
    )

    while True:
        schedule.run_pending()
        time.sleep(60)


# ── ENTRYPOINT ────────────────────────────────────────────

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

        elif sys.argv[1] == 'brief':
            send_morning_brief()

        elif sys.argv[1] == 'review':
            send_weekly_review()

    else:
        run_bot()
