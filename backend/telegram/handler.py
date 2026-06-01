import os
import logging
import requests
import time
from dotenv import load_dotenv
load_dotenv(os.path.expanduser('~/sentinel/.env'))

logger = logging.getLogger(__name__)

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

def send(message: str):
    if not TOKEN or not CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/"
            f"bot{TOKEN}/sendMessage",
            json={
                'chat_id': CHAT_ID,
                'text': message,
                'parse_mode': 'HTML'
            },
            timeout=10
        )
    except Exception as e:
        logger.error(f"Telegram send error: {e}")

def get_updates(offset=None):
    try:
        params = {'timeout': 30}
        if offset:
            params['offset'] = offset
        r = requests.get(
            f"https://api.telegram.org/"
            f"bot{TOKEN}/getUpdates",
            params=params,
            timeout=35
        )
        return r.json()
    except Exception as e:
        logger.error(f"Get updates error: {e}")
        return {'ok': False, 'result': []}

def handle_command(text: str) -> str:
    text = text.strip().lower()

    try:
        # SCAN
        if text in ('scan', '/scan'):
            send("🔍 Scanning 43 tickers...")
            from backend.market_data.fetcher import fetch
            from backend.strategies.scanner import scan
            from backend.configs.symbols import SCAN_PRIORITY

            spy = fetch('SPY', '1y')
            signals = []

            for ticker in SCAN_PRIORITY[:20]:
                data = fetch(ticker, '1y')
                if data and spy:
                    signal = scan(
                        ticker, data.df, spy.df
                    )
                    if signal and signal.action in (
                        'READY', 'WATCH'
                    ):
                        signals.append(signal)

            if not signals:
                return (
                    "📡 Scan complete\n"
                    "No setups found right now\n"
                    "Market conditions not ideal"
                )

            msg = f"📡 Found {len(signals)} setups\n\n"
            for s in signals[:3]:
                emoji = (
                    '🟢' if s.action == 'READY'
                    else '🟡'
                )
                msg += (
                    f"{emoji} {s.ticker} — "
                    f"{s.action}\n"
                    f"Score: {s.score}/100\n"
                    f"Entry: ${s.entry:.2f}\n"
                    f"Stop: ${s.stop:.2f}\n"
                    f"Target: ${s.target1:.2f}\n\n"
                )
            return msg

        # TOP 3
        elif text in ('top3', '/top3', 'top'):
            send("🏆 Ranking ETFs and stocks...")
            from backend.strategies.ranker import (
                run_ranking
            )
            from backend.market_data.fetcher import fetch

            all_ranks, top3 = run_ranking(fetch)

            if not top3:
                return "No top picks right now"

            msg = "🏆 TOP 3 RIGHT NOW\n\n"
            for i, r in enumerate(top3):
                emoji = (
                    '🟢' if r.action == 'READY'
                    else '🟡'
                )
                msg += (
                    f"{i+1}. {emoji} {r.ticker}\n"
                    f"Score: {r.composite_score}/100\n"
                    f"Sector: {r.sector}\n"
                    f"RSI: {r.rsi:.0f}\n\n"
                )
            return msg

        # ANALYZE ticker
        elif text.startswith('analyze ') or \
             text.startswith('/analyze '):
            ticker = text.split(' ')[-1].upper()

            from backend.market_data.fetcher import fetch
            from backend.strategies.scanner import (
                scan, calculate_indicators
            )
            from backend.ai.summarizer import (
                explain_setup
            )

            data = fetch(ticker, '1y')
            spy = fetch('SPY', '1y')

            if not data:
                return f"No data for {ticker}"

            ind = calculate_indicators(data.df)
            if not ind:
                return f"Cannot analyze {ticker}"

            signal = scan(ticker, data.df, spy.df)

            above_ema21 = ind['close'] > ind['ema21']
            above_ema50 = ind['close'] > ind['ema50']

            msg = (
                f"📊 {ticker} ANALYSIS\n\n"
                f"Price: ${ind['close']:.2f}\n"
                f"RSI: {ind['rsi']:.0f}\n"
                f"Volume: {ind['volume_ratio']:.1f}x avg\n"
                f"ATR: {ind['atr_pct']:.1f}%\n\n"
                f"EMA21: "
                f"{'✅ Above' if above_ema21 else '❌ Below'}\n"
                f"EMA50: "
                f"{'✅ Above' if above_ema50 else '❌ Below'}\n\n"
            )

            if signal:
                msg += (
                    f"Signal: {signal.action}\n"
                    f"Strategy: {signal.strategy}\n"
                    f"Score: {signal.score}/100\n"
                    f"Entry: ${signal.entry:.2f}\n"
                    f"Stop: ${signal.stop:.2f}\n"
                    f"Target: ${signal.target1:.2f}\n\n"
                )
                ai = explain_setup(
                    ticker, signal.strategy,
                    signal.score, ind
                )
                msg += f"AI: {ai[:150]}"
            else:
                msg += "No setup detected today"

            return msg

        # PORTFOLIO
        elif text in (
            'portfolio', '/portfolio', 'port'
        ):
            from backend.portfolio.tracker import (
                PortfolioTracker
            )
            from backend.journal.logger import Journal

            tracker = PortfolioTracker()
            journal = Journal()
            positions = tracker.get_open_positions()
            stats = journal.get_stats()
            budget = float(
                os.getenv('SWING_BUDGET', '300')
            )

            total_cost = sum(
                p.get('shares', 0) *
                p.get('entry_price', 0)
                for p in positions
            )
            available = max(budget - total_cost, 0)

            msg = (
                f"💼 PORTFOLIO\n\n"
                f"Budget: ${budget:.0f}\n"
                f"Available: ${available:.2f}\n"
                f"Positions: {len(positions)}/3\n\n"
            )

            if positions:
                msg += "OPEN POSITIONS\n"
                for p in positions:
                    msg += (
                        f"• {p['ticker']} "
                        f"@ ${p['entry_price']:.2f}\n"
                    )
            else:
                msg += "No open positions\n"

            msg += (
                f"\nPERFORMANCE\n"
                f"Trades: "
                f"{stats.get('total_trades', 0)}\n"
                f"Win rate: "
                f"{stats.get('win_rate', 0):.0f}%\n"
                f"Total PnL: "
                f"${stats.get('total_pnl', 0):+.2f}\n"
            )

            return msg

        # STATS
        elif text in ('stats', '/stats'):
            from backend.journal.logger import Journal
            journal = Journal()
            stats = journal.get_stats()
            breakdown = journal.get_strategy_breakdown()

            msg = (
                f"📈 PERFORMANCE STATS\n\n"
                f"Total trades: "
                f"{stats.get('total_trades', 0)}\n"
                f"Win rate: "
                f"{stats.get('win_rate', 0):.0f}%\n"
                f"Total PnL: "
                f"${stats.get('total_pnl', 0):+.2f}\n"
                f"Profit factor: "
                f"{stats.get('profit_factor', 0):.2f}\n"
                f"Best trade: "
                f"{stats.get('best_trade', 0):+.2f}\n\n"
            )

            if breakdown:
                msg += "BY STRATEGY\n"
                for strat, data in breakdown.items():
                    msg += (
                        f"• {strat}: "
                        f"{data.get('win_rate',0):.0f}% WR "
                        f"${data['total_pnl']:+.2f}\n"
                    )

            return msg

        # GOAL
        elif text in ('goal', '/goal', 'car'):
            from backend.journal.logger import Journal
            journal = Journal()
            stats = journal.get_stats()

            budget = float(
                os.getenv('SWING_BUDGET', '300')
            )
            total_pnl = stats.get('total_pnl', 0)
            car_goal = 40000
            saved = budget + total_pnl
            progress = (saved / car_goal) * 100
            weeks_left = int(
                (car_goal - saved) / budget
            ) if budget > 0 else 0
            years = weeks_left // 52
            months = (weeks_left % 52) // 4

            return (
                f"🎯 CAR GOAL\n\n"
                f"Target: $40,000\n"
                f"Saved: ${saved:.2f}\n"
                f"Progress: {progress:.2f}%\n\n"
                f"Weekly: ${budget:.0f}\n"
                f"Timeline: ~{years}y {months}m\n\n"
                f"Keep going! 💪"
            )

        # PAUSE
        elif text in ('pause', '/pause'):
            return (
                "⏸ Bot paused\n"
                "Text 'resume' to restart scanning"
            )

        # RESUME
        elif text in ('resume', '/resume'):
            return (
                "▶️ Bot resumed\n"
                "Scanning every 45 minutes"
            )

        # HELP
        elif text in ('help', '/help', '/start'):
            return (
                "⚡ SENTINEL COMMANDS\n\n"
                "scan — Run full market scan\n"
                "top3 — Best 3 opportunities\n"
                "analyze NVDA — Analyze any stock\n"
                "portfolio — Your positions\n"
                "stats — Performance stats\n"
                "goal — Car fund progress\n"
                "pause — Stop scanning\n"
                "resume — Start scanning\n"
                "help — Show this menu\n\n"
                "Dashboard: http://localhost:8501"
            )

        else:
            return (
                "Unknown command.\n"
                "Text 'help' for all commands."
            )

    except Exception as e:
        logger.error(f"Command error: {e}")
        return f"Error: {str(e)[:100]}"

def start_listener():
    logger.info("Telegram listener started")
    offset = None

    while True:
        try:
            updates = get_updates(offset)

            if not updates.get('ok'):
                time.sleep(5)
                continue

            for update in updates.get('result', []):
                offset = update['update_id'] + 1

                message = update.get('message', {})
                chat_id = message.get(
                    'chat', {}
                ).get('id', '')
                text = message.get('text', '')

                if str(chat_id) != str(CHAT_ID):
                    continue

                if text:
                    logger.info(
                        f"Command received: {text}"
                    )
                    response = handle_command(text)
                    send(response)

        except Exception as e:
            logger.error(f"Listener error: {e}")
            time.sleep(5)
