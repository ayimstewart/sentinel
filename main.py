import os
import time
import logging
import threading
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
from backend.ai.summarizer import explain_setup
from backend.configs.symbols import (
    MARKET_FILTERS,
    SCAN_PRIORITY,
    MY_ROBINHOOD_STOCKS,
    ETF_LONG_TERM,
    get_sector,
)
from backend.telegram.handler import start_listener
from database import Database

try:
    from thermal_monitor import thermal
except ImportError:
    thermal = None

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
)
logger = logging.getLogger(__name__)

tracker = PortfolioTracker()
journal = Journal()
db = Database()

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


# ── SIGNAL ALERT ─────────────────────────────────────────

def _send_signals_telegram(signals: list):
    if not signals:
        return
    for sig in signals[:3]:
        hold = sig.get('hold_plan', {})
        emoji = '🟢' if sig.get('action') == 'READY' else '🟡'
        msg = (
            f"⚡ SWING SIGNAL\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{emoji} {sig['ticker']} — {sig.get('action')}\n"
            f"Strategy: {sig.get('strategy')}\n"
            f"Score: {sig.get('score')}/100\n\n"
            f"TRADE PLAN\n"
            f"Entry:    ${sig.get('entry', 0):.2f}\n"
            f"Stop:     ${sig.get('stop', 0):.2f} "
            f"(-{hold.get('risk_pct', 3)}%)\n"
            f"Target 1: ${sig.get('target1', 0):.2f} "
            f"(+{hold.get('reward_pct', 8)}%)\n"
            f"Target 2: ${sig.get('target2', 0):.2f}\n\n"
            f"HOLD PLAN\n"
            f"Duration: "
            f"{hold.get('hold_estimate', '3-7 days')}\n"
            f"R/R Ratio: "
            f"1:{hold.get('rr_ratio', 2.5)}\n\n"
            f"EXIT RULES\n"
        )
        for rule in hold.get('exit_rules', []):
            msg += f"• {rule}\n"
        msg += (
            f"\n📱 ROBINHOOD STEPS:\n"
            f"1. Open Robinhood\n"
            f"2. Search {sig['ticker']}\n"
            f"3. Buy ${sig.get('cost', 0):.2f} worth\n"
            f"4. Set stop at ${sig.get('stop', 0):.2f}\n\n"
            f"Check dashboard to approve:"
            f"\nhttp://localhost:8501"
        )
        _send_telegram(msg)


# ── MORNING BRIEF ─────────────────────────────────────────

def send_morning_brief():
    try:
        spy_data = fetch('SPY', '1y')
        qqq_data = fetch('QQQ', '1mo')

        spy_chg = 0.0
        qqq_chg = 0.0

        if spy_data and len(spy_data.df) >= 2:
            spy_chg = round(
                (float(spy_data.df['Close'].iloc[-1]) -
                 float(spy_data.df['Close'].iloc[-2])) /
                float(spy_data.df['Close'].iloc[-2]) * 100, 2
            )

        if qqq_data and len(qqq_data.df) >= 2:
            qqq_chg = round(
                (float(qqq_data.df['Close'].iloc[-1]) -
                 float(qqq_data.df['Close'].iloc[-2])) /
                float(qqq_data.df['Close'].iloc[-2]) * 100, 2
            )

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
            f"Positions: {len(positions)}/3\n"
            f"Budget: ${budget:.0f}\n\n"
        )

        if signals:
            ready = [s for s in signals if s.get('action') == 'READY']
            watch = [s for s in signals if s.get('action') == 'WATCH']

            if ready:
                msg += f"🟢 READY ({len(ready)}):\n"
                for s in ready[:3]:
                    msg += f"  {s['ticker']} score={s['score']}\n"
            if watch:
                msg += f"🟡 WATCH ({len(watch)}):\n"
                for s in watch[:3]:
                    msg += f"  {s['ticker']} score={s['score']}\n"
            msg += "\nOpen dashboard to approve"
        else:
            msg += (
                "No setups today\n"
                "Waiting for better conditions"
            )

        # Check Robinhood stocks for setups
        rh_setups = []
        for ticker in MY_ROBINHOOD_STOCKS:
            try:
                data = fetch(ticker, '1y')
                if data and spy_data:
                    signal = scan(ticker, data.df, spy_data.df)
                    if signal and signal.action in ('READY', 'WATCH'):
                        rh_setups.append({
                            'ticker': ticker,
                            'action': signal.action,
                            'score': signal.score,
                            'strategy': signal.strategy,
                        })
            except Exception:
                pass

        if rh_setups:
            msg += f"\n📱 YOUR STOCKS:\n"
            for s in rh_setups:
                emoji = '🟢' if s['action'] == 'READY' else '🟡'
                msg += (
                    f"{emoji} {s['ticker']} "
                    f"— {s['action']} "
                    f"({s['score']}/100)\n"
                )

        msg += "\n\nDashboard: http://localhost:8501"

        _send_telegram(msg)
        logger.info("Morning brief sent")

    except Exception as e:
        logger.error(f"Morning brief error: {e}")


# ── EXIT ALERTS ───────────────────────────────────────────

def check_exit_alerts():
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
            if not data or data.df.empty:
                continue

            current = float(data.df['Close'].iloc[-1])
            pnl_pct = (
                (current - entry) / entry * 100
                if entry > 0 else 0
            )

            if current <= stop * 1.02:
                _send_telegram(
                    f"🛑 STOP ALERT — {ticker}\n"
                    f"Price: ${current:.2f}\n"
                    f"Stop: ${stop:.2f}\n"
                    f"PnL: {pnl_pct:+.1f}%\n\n"
                    f"Consider selling on Robinhood"
                )
                logger.warning(f"Stop alert: {ticker}")

            elif target1 > 0 and current >= target1 * 0.99:
                _send_telegram(
                    f"🎯 TARGET HIT — {ticker}\n"
                    f"Price: ${current:.2f}\n"
                    f"Target: ${target1:.2f}\n"
                    f"PnL: {pnl_pct:+.1f}%\n\n"
                    f"Consider selling 50% on Robinhood"
                )
                logger.info(f"Target alert: {ticker}")

        except Exception as e:
            logger.error(f"Exit check {ticker}: {e}")


# ── WEEKLY REVIEW ─────────────────────────────────────────

def send_weekly_review():
    try:
        stats = journal.get_stats()
        positions = tracker.get_open_positions()
        breakdown = journal.get_strategy_breakdown()

        budget = float(os.getenv('SWING_BUDGET', '300'))
        total_pnl = stats.get('total_pnl', 0)
        car_goal = 40000
        saved = budget + total_pnl
        progress = (saved / car_goal) * 100

        msg = (
            f"📊 SENTINEL WEEKLY REVIEW\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"PERFORMANCE\n"
            f"Trades: {stats.get('total_trades', 0)}\n"
            f"Win rate: {stats.get('win_rate', 0):.0f}%\n"
            f"Total PnL: ${total_pnl:+.2f}\n"
            f"Profit factor: {stats.get('profit_factor', 0):.2f}\n\n"
        )

        if breakdown:
            msg += "STRATEGY BREAKDOWN\n"
            for strat, data in breakdown.items():
                msg += (
                    f"{strat}: "
                    f"{data['trades']} trades | "
                    f"{data.get('win_rate', 0):.0f}% WR | "
                    f"${data['total_pnl']:+.2f}\n"
                )
            msg += "\n"

        msg += (
            f"POSITIONS\n"
            f"Open: {len(positions)}/3\n\n"
            f"🎯 CAR GOAL\n"
            f"${saved:.2f} / $40,000\n"
            f"Progress: {progress:.2f}%\n\n"
            f"Have a great weekend! 💪"
        )

        _send_telegram(msg)
        logger.info("Weekly review sent")

    except Exception as e:
        logger.error(f"Weekly review error: {e}")


# ── SCAN ──────────────────────────────────────────────────

def run_scan():
    if not is_market_open():
        logger.info('Market closed — skipping')
        return

    if thermal and thermal.capacity == 0:
        logger.warning('Thermal critical')
        return

    logger.info("Starting scan...")

    watchlist = db.get_watchlist()
    tickers = [w['ticker'] for w in watchlist]

    logger.info(f"Scanning {len(tickers)} stocks")

    spy_data = fetch('SPY', '1y')
    if not spy_data:
        logger.error("Cannot fetch SPY")
        return

    portfolio_value = get_portfolio_value()
    open_positions = tracker.get_open_positions()
    daily_pnl = 0.0

    signals_found = []

    for ticker in tickers:
        try:
            data = fetch(ticker, '1y')
            if not data:
                journal.log_rejection(
                    ticker, 'No data', 'data'
                )
                continue

            signal = scan(ticker, data.df, spy_data.df)
            if not signal:
                journal.log_rejection(
                    ticker,
                    'No strategy triggered',
                    'strategy'
                )
                continue

            portfolio = Portfolio(
                positions=open_positions,
                portfolio_value=portfolio_value,
                cash=portfolio_value,
                daily_pnl=daily_pnl
            )

            risk = evaluate(signal, portfolio)
            if not risk.allowed:
                journal.log_rejection(
                    ticker, risk.reason, 'risk'
                )
                continue

            try:
                explanation = explain_setup(
                    ticker, signal.strategy,
                    signal.score,
                    {'close': signal.entry,
                     'ema21': signal.entry,
                     'rsi': 50,
                     'volume_ratio': 1.2,
                     'atr_pct': 2.0}
                )
            except Exception:
                explanation = (
                    f"{signal.strategy} setup"
                )

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
                reason=signal.reason
            )

            signals_found.append({
                'id': signal_id,
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
                'explanation': explanation,
                'hold_plan': signal.hold_plan,
            })

            logger.info(
                f"✅ {ticker}: {signal.action} "
                f"score={signal.score}"
            )

            time.sleep(2)

        except Exception as e:
            logger.error(f"{ticker} error: {e}")

    if signals_found:
        _send_signals_telegram(signals_found)

    logger.info(
        f"Scan done — {len(signals_found)} signals"
    )
    return signals_found


# ── TRADE EXECUTION ───────────────────────────────────────

def execute_approved_trade(signal_data: dict):
    ticker = signal_data['ticker']
    shares = signal_data.get('shares', 0)
    entry = signal_data.get('entry', 0)
    stop = signal_data.get('stop', 0)
    target1 = signal_data.get('target1', 0)

    results = {}

    # 1. Execute on Alpaca paper
    try:
        from backend.execution.broker import place_buy
        order = place_buy(
            ticker=ticker,
            shares=shares,
            note="Sentinel signal approved"
        )

        if order.success:
            results['alpaca'] = 'executed'
            logger.info(
                f"Alpaca paper trade: "
                f"{ticker} {shares} shares"
            )
        else:
            results['alpaca'] = 'failed'

    except Exception as e:
        results['alpaca'] = f'error: {e}'
        logger.error(f"Alpaca execution error: {e}")

    # 2. Send Robinhood manual alert
    cost = round(shares * entry, 2)
    msg = (
        f"📱 BUY ON ROBINHOOD NOW\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Stock: {ticker}\n"
        f"Shares: {shares:.4f}\n"
        f"Price: ${entry:.2f}\n"
        f"Total: ${cost:.2f}\n\n"
        f"Stop loss: ${stop:.2f}\n"
        f"Target 1: ${target1:.2f} (+8%)\n\n"
        f"Steps:\n"
        f"1. Open Robinhood\n"
        f"2. Search {ticker}\n"
        f"3. Buy {shares:.4f} shares\n"
        f"4. Set stop at ${stop:.2f}\n\n"
        f"Also executing on Alpaca paper ✅"
    )
    _send_telegram(msg)

    # 3. Track position
    tracker.open_position(
        ticker=ticker,
        shares=shares,
        entry_price=entry,
        stop_price=stop,
        target1=target1,
        target2=target1 * 1.07,
        strategy=signal_data.get('strategy', '')
    )

    journal.log_trade_open(
        ticker=ticker,
        strategy=signal_data.get('strategy', ''),
        shares=shares,
        entry_price=entry,
        stop=stop,
        target1=target1,
        target2=target1 * 1.07
    )

    return results


# ── DAILY POSITION UPDATE ─────────────────────────────────

def daily_position_update():
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

            progress = (
                (current - entry) /
                (target1 - entry) * 100
            ) if target1 > entry else 0
            progress = max(0, min(100, progress))

            action = "HOLD ✅"
            if current <= stop * 1.02:
                action = "⚠️ NEAR STOP — CONSIDER SELLING"
            elif current >= target1 * 0.99:
                action = "🎯 TARGET HIT — SELL HALF"
            elif pnl_pct < -2:
                action = "⚠️ WEAKENING — WATCH CLOSELY"

            msg = (
                f"📊 DAILY UPDATE — {ticker}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"Entry:   ${entry:.2f}\n"
                f"Current: ${current:.2f}\n"
                f"PnL:     {pnl_pct:+.1f}%\n\n"
                f"Stop:    ${stop:.2f}\n"
                f"Target:  ${target1:.2f}\n"
                f"Progress: {progress:.0f}% to target\n\n"
                f"ACTION: {action}\n\n"
                f"Morning check:\n"
                f"• Below ${stop:.2f} → SELL ALL\n"
                f"• Above ${target1:.2f} → SELL HALF\n"
                f"• Between → HOLD"
            )

            _send_telegram(msg)

        except Exception as e:
            logger.error(
                f"Daily update {ticker}: {e}"
            )


# ── WEEKLY DISCOVERY ──────────────────────────────────────

def run_weekly_discovery():
    from backend.strategies.discovery import (
        auto_add_discoveries, DISCOVERY_UNIVERSE
    )
    _send_telegram(
        "🔍 Running weekly stock discovery...\n"
        "Scanning 500+ stocks for opportunities"
    )

    try:
        added, discoveries = auto_add_discoveries(
            fetch, db, min_score=75.0
        )

        msg = (
            f"🔍 DISCOVERY COMPLETE\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Scanned: {len(DISCOVERY_UNIVERSE)} stocks\n"
            f"Found: {len(discoveries)} opportunities\n"
            f"Auto-added: {len(added)} new stocks\n\n"
        )

        if discoveries:
            msg += "TOP DISCOVERIES:\n"
            for d in discoveries[:5]:
                msg += (
                    f"• {d.ticker} "
                    f"score={d.score} "
                    f"{d.action}\n"
                    f"  {d.reason}\n"
                )

        if added:
            msg += (
                f"\nAdded to watchlist: "
                f"{', '.join(added)}"
            )

        _send_telegram(msg)

    except Exception as e:
        logger.error(f"Weekly discovery error: {e}")
        _send_telegram(f"Discovery error: {e}")


# ── BOT RUNNER ────────────────────────────────────────────

def run_bot():
    logger.info("⚡ SENTINEL starting...")
    logger.info(f"ETFs: {SCAN_PRIORITY}")

    journal.log_event('BOT_START', 'Sentinel started')

    _send_telegram(
        f"⚡ Sentinel started\n"
        f"Scanning every 45 minutes\n"
        f"Morning brief at 9am EST\n"
        f"Dashboard: http://localhost:8501"
    )

    # Start Telegram command listener
    telegram_thread = threading.Thread(
        target=start_listener,
        daemon=True
    )
    telegram_thread.start()
    logger.info("Telegram listener active")

    run_scan()

    # Morning brief weekdays only
    schedule.every().monday.at("09:00").do(send_morning_brief)
    schedule.every().tuesday.at("09:00").do(send_morning_brief)
    schedule.every().wednesday.at("09:00").do(send_morning_brief)
    schedule.every().thursday.at("09:00").do(send_morning_brief)
    schedule.every().friday.at("09:00").do(send_morning_brief)

    schedule.every(45).minutes.do(run_scan)
    schedule.every(30).minutes.do(check_exit_alerts)
    schedule.every().day.at("10:00").do(
        daily_position_update
    )
    schedule.every().sunday.at("17:00").do(
        run_weekly_discovery
    )
    schedule.every().sunday.at("18:00").do(send_weekly_review)

    logger.info(
        "Schedule active:\n"
        "  Scan: every 45 min\n"
        "  Morning brief: 9am weekdays\n"
        "  Exit checks: every 30 min\n"
        "  Daily update: 10am daily\n"
        "  Discovery: Sunday 5pm\n"
        "  Weekly review: Sunday 6pm"
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
