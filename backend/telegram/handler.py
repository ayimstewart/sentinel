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

def analyze_single(ticker: str) -> str:
    try:
        from backend.market_data.fetcher import fetch
        from backend.strategies.scanner import (
            scan, calculate_indicators
        )
        from backend.ai.summarizer import explain_setup
        import os
        from dotenv import load_dotenv
        load_dotenv(
            os.path.expanduser('~/sentinel/.env')
        )

        data = fetch(ticker, '2y')
        spy = fetch('SPY', '2y')

        if not data or data.df.empty:
            return (
                f"No data for {ticker}\n"
                f"Check ticker is correct"
            )

        ind = calculate_indicators(data.df)
        spy_ind = calculate_indicators(spy.df) \
                  if spy else None

        if not ind:
            return f"Cannot analyze {ticker}"

        price = ind['close']
        rsi = ind['rsi']

        # ── SHORT TERM (swing 1-2 weeks) ──
        st_score = 0

        above_ema20 = price > ind['ema20']
        above_ema50 = price > ind['ema50']
        ema9_above_21 = ind['ema9'] > ind['ema21']
        rsi_healthy = 40 <= rsi <= 65
        vol_ok = ind.get('volume_ratio', 0) >= 0.8

        if above_ema20: st_score += 20
        if above_ema50: st_score += 20
        if ema9_above_21: st_score += 20
        if rsi_healthy: st_score += 20
        if vol_ok: st_score += 10

        rs = 0
        if spy_ind:
            rs = (
                ind.get('roc20', 0) -
                spy_ind.get('roc20', 0)
            )
        if rs > 0: st_score += 10

        if rsi > 75: st_score -= 20
        if rsi < 35: st_score -= 10

        st_score = max(0, min(100, st_score))

        if st_score >= 70:
            st_verdict = '🟢 GOOD SWING ENTRY'
        elif st_score >= 50:
            st_verdict = '🟡 WAIT FOR PULLBACK'
        elif st_score >= 30:
            st_verdict = '🟠 NOT YET'
        else:
            st_verdict = '🔴 AVOID NOW'

        entry = round(price, 2)
        stop = round(price * 0.97, 2)
        target1 = round(price * 1.08, 2)
        target2 = round(price * 1.15, 2)

        # ── LONG TERM (months to years) ──
        lt_score = 0

        above_200 = price > ind['ema200']
        pct_vs_200 = (
            (price - ind['ema200']) /
            ind['ema200'] * 100
        )
        ema_aligned = (
            ind['ema20'] > ind['ema50'] >
            ind['ema200']
        )

        close = data.df['Close']
        one_yr_bars = min(252, len(close) - 1)
        yr_return = (
            (price - float(close.iloc[-one_yr_bars])) /
            float(close.iloc[-one_yr_bars]) * 100
        )
        two_yr_return = (
            (price - float(close.iloc[0])) /
            float(close.iloc[0]) * 100
        )

        high_52 = float(data.df['High'].tail(252).max())
        low_52 = float(data.df['Low'].tail(252).min())
        from_high = (price - high_52) / high_52 * 100
        from_low = (price - low_52) / low_52 * 100

        if above_200: lt_score += 35
        if ema_aligned: lt_score += 25
        if yr_return > 0: lt_score += 15
        if two_yr_return > 0: lt_score += 10
        if rsi < 70: lt_score += 10
        if pct_vs_200 < 20: lt_score += 5

        lt_score = max(0, min(100, lt_score))

        if lt_score >= 75:
            lt_verdict = '✅ STRONG HOLD/BUY'
        elif lt_score >= 55:
            lt_verdict = '👀 ACCUMULATE SLOWLY'
        elif lt_score >= 35:
            lt_verdict = '⏳ WAIT — NOT READY'
        else:
            lt_verdict = '❌ AVOID LONG TERM'

        if rsi > 75:
            rsi_note = 'Overbought ⚠️'
        elif rsi > 60:
            rsi_note = 'Bullish 📈'
        elif rsi < 35:
            rsi_note = 'Oversold 👀'
        elif rsi < 45:
            rsi_note = 'Bearish 📉'
        else:
            rsi_note = 'Neutral 😐'

        if price > ind['ema20'] > ind['ema50'] > ind['ema200']:
            trend = '🟢 STRONG UPTREND'
        elif price > ind['ema50'] > ind['ema200']:
            trend = '🟢 UPTREND'
        elif price > ind['ema200']:
            trend = '🟡 ABOVE 200 EMA'
        elif price < ind['ema200']:
            trend = '🔴 DOWNTREND'
        else:
            trend = '🟡 MIXED'

        try:
            ai_note = explain_setup(
                ticker, 'ANALYSIS',
                st_score, ind
            )[:180]
        except Exception:
            ai_note = ''

        msg = (
            f"📊 {ticker} — FULL ANALYSIS\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Price:  ${price:.2f}\n"
            f"Trend:  {trend}\n"
            f"RSI:    {rsi:.0f} — {rsi_note}\n"
            f"RS SPY: {rs:+.1f}%\n\n"
            f"52 WEEK\n"
            f"High: ${high_52:.2f} "
            f"({from_high:.1f}% away)\n"
            f"Low:  ${low_52:.2f} "
            f"({from_low:+.1f}% above)\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📅 SHORT TERM (1-2 weeks)\n"
            f"Score:  {st_score}/100\n"
            f"Signal: {st_verdict}\n"
            f"Entry:  ${entry:.2f}\n"
            f"Stop:   ${stop:.2f} (-3%)\n"
            f"Target: ${target1:.2f} (+8%)\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📈 LONG TERM (months+)\n"
            f"Score:    {lt_score}/100\n"
            f"Signal:   {lt_verdict}\n"
            f"vs EMA200: {pct_vs_200:+.1f}%\n"
            f"1Y Return: {yr_return:+.1f}%\n"
            f"2Y Return: {two_yr_return:+.1f}%\n"
        )

        if ai_note:
            msg += (
                f"\n━━━━━━━━━━━━━━━━━━━━\n"
                f"🧠 AI NOTE\n{ai_note}"
            )

        return msg

    except Exception as e:
        return (
            f"Analysis error {ticker}:\n"
            f"{str(e)[:100]}"
        )


def analyze_multiple(tickers: list) -> str:
    if len(tickers) > 15:
        return (
            f"Too many ({len(tickers)}).\n"
            f"Max 15 at once."
        )

    send(
        f"🔍 Analyzing {len(tickers)} stocks...\n"
        f"This takes 1-2 minutes."
    )

    all_results = []

    for ticker in tickers:
        try:
            from backend.market_data.fetcher import fetch
            from backend.strategies.scanner import (
                calculate_indicators
            )

            data = fetch(ticker, '2y')
            spy = fetch('SPY', '2y')

            if not data or data.df.empty:
                all_results.append(
                    f"⚠️ {ticker}: No data available\n"
                )
                continue

            ind = calculate_indicators(data.df)
            spy_ind = calculate_indicators(spy.df) \
                      if spy else None

            if not ind:
                all_results.append(
                    f"⚠️ {ticker}: Cannot calculate\n"
                )
                continue

            price = ind['close']
            rsi = ind['rsi']

            # SHORT TERM SCORE
            st_score = 0
            if price > ind['ema20']: st_score += 20
            if price > ind['ema50']: st_score += 20
            if ind['ema9'] > ind['ema21']: st_score += 20
            if 40 <= rsi <= 65: st_score += 20
            if ind.get('volume_ratio', 0) >= 0.8:
                st_score += 10

            rs = 0
            if spy_ind:
                rs = (
                    ind.get('roc20', 0) -
                    spy_ind.get('roc20', 0)
                )
            if rs > 0: st_score += 10
            if rsi > 75: st_score -= 20
            st_score = max(0, min(100, st_score))

            # LONG TERM SCORE
            lt_score = 0
            above_200 = price > ind['ema200']
            ema_aligned = (
                ind['ema20'] > ind['ema50'] >
                ind['ema200']
            )
            pct_vs_200 = (
                (price - ind['ema200']) /
                ind['ema200'] * 100
            )

            close = data.df['Close']
            one_yr = min(252, len(close) - 1)
            yr_return = (
                (price - float(close.iloc[-one_yr])) /
                float(close.iloc[-one_yr]) * 100
            )
            two_yr_return = (
                (price - float(close.iloc[0])) /
                float(close.iloc[0]) * 100
            )

            high_52 = float(
                data.df['High'].tail(252).max()
            )
            low_52 = float(
                data.df['Low'].tail(252).min()
            )
            from_high = (
                (price - high_52) / high_52 * 100
            )

            if above_200: lt_score += 35
            if ema_aligned: lt_score += 25
            if yr_return > 0: lt_score += 15
            if two_yr_return > 0: lt_score += 10
            if rsi < 70: lt_score += 10
            if pct_vs_200 < 20: lt_score += 5
            lt_score = max(0, min(100, lt_score))

            # TREND
            if (price > ind['ema20'] >
                    ind['ema50'] > ind['ema200']):
                trend = '🟢 STRONG UPTREND'
            elif price > ind['ema50'] > ind['ema200']:
                trend = '🟢 UPTREND'
            elif price > ind['ema200']:
                trend = '🟡 ABOVE 200 EMA'
            else:
                trend = '🔴 DOWNTREND'

            # RSI NOTE
            if rsi > 75:
                rsi_note = 'Overbought ⚠️'
            elif rsi > 60:
                rsi_note = 'Bullish'
            elif rsi < 35:
                rsi_note = 'Oversold 👀'
            elif rsi < 45:
                rsi_note = 'Bearish'
            else:
                rsi_note = 'Neutral'

            # SHORT TERM VERDICT
            if st_score >= 70:
                st_verdict = '🟢 BUY NOW'
            elif st_score >= 50:
                st_verdict = '🟡 WAIT'
            elif st_score >= 30:
                st_verdict = '🟠 NOT YET'
            else:
                st_verdict = '🔴 AVOID'

            # LONG TERM VERDICT
            if lt_score >= 75:
                lt_verdict = '✅ BUY/ACCUMULATE'
            elif lt_score >= 55:
                lt_verdict = '👀 WATCH — ADD SLOWLY'
            elif lt_score >= 35:
                lt_verdict = '⏳ WAIT FOR UPTREND'
            else:
                lt_verdict = '❌ AVOID'

            # OVERALL VERDICT
            combined = (st_score + lt_score) / 2
            if combined >= 65:
                overall = '💪 WORTH BUYING'
            elif combined >= 45:
                overall = '👀 WATCHLIST ONLY'
            else:
                overall = '❌ NOT WORTH IT NOW'

            entry = round(price, 2)
            stop = round(price * 0.97, 2)
            target1 = round(price * 1.08, 2)

            result = (
                f"{'='*35}\n"
                f"📊 {ticker}\n"
                f"{'='*35}\n"
                f"Price:  ${price:.2f}\n"
                f"Trend:  {trend}\n"
                f"RSI:    {rsi:.0f} — {rsi_note}\n"
                f"RS SPY: {rs:+.1f}%\n"
                f"52W High: ${high_52:.2f} "
                f"({from_high:.1f}%)\n"
                f"1Y Return: {yr_return:+.1f}%\n"
                f"2Y Return: {two_yr_return:+.1f}%\n"
                f"\n"
                f"📅 SHORT TERM\n"
                f"Score:  {st_score}/100\n"
                f"Signal: {st_verdict}\n"
                f"Entry:  ${entry:.2f}\n"
                f"Stop:   ${stop:.2f}\n"
                f"Target: ${target1:.2f} (+8%)\n"
                f"\n"
                f"📈 LONG TERM\n"
                f"Score:    {lt_score}/100\n"
                f"Signal:   {lt_verdict}\n"
                f"vs EMA200: {pct_vs_200:+.1f}%\n"
                f"\n"
                f"⭐ VERDICT\n"
                f"{overall}\n"
            )

            all_results.append(result)

        except Exception as e:
            all_results.append(
                f"⚠️ {ticker}: Error — "
                f"{str(e)[:50]}\n"
            )

    for result in all_results:
        send(result)

    summary = (
        f"{'='*35}\n"
        f"📋 SUMMARY\n"
        f"{'='*35}\n"
        f"Analyzed: {len(all_results)} stocks\n\n"
    )

    return summary


def handle_command(text: str) -> str:
    text = text.strip().lower()

    try:
        # SCAN
        if text in ('scan', '/scan'):
            send("🔍 Scanning watchlist...")
            from backend.market_data.fetcher import fetch
            from backend.strategies.scanner import scan
            from database import Database
            db = Database()
            watchlist = db.get_watchlist()
            tickers = [w['ticker'] for w in watchlist]

            spy = fetch('SPY', '1y')
            signals = []

            for ticker in tickers[:20]:
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

        # ANALYZE ticker(s) — short + long term view
        elif text.startswith('analyze ') or \
             text.startswith('/analyze '):
            parts = text.split()[1:]
            tickers = [t.upper() for t in parts if t]
            if not tickers:
                return (
                    "Usage: analyze NVDA\n"
                    "or: analyze FSLR NEE ENPH"
                )
            if len(tickers) == 1:
                send(f"📊 Analyzing {tickers[0]}...")
                return analyze_single(tickers[0])
            send(
                f"📊 Analyzing "
                f"{len(tickers)} stocks..."
            )
            return analyze_multiple(tickers)

        # LONGTERM / LT — long term focus
        elif (text.startswith('longterm ') or
              text.startswith('/longterm ') or
              text.startswith('lt ') or
              text.startswith('/lt ')):
            parts = text.split()[1:]
            tickers = [t.upper() for t in parts if t]
            if not tickers:
                return (
                    "Usage: lt NVDA\n"
                    "or: lt FSLR NEE ENPH"
                )
            if len(tickers) == 1:
                send(
                    f"📈 Analyzing {tickers[0]}..."
                )
                return analyze_single(tickers[0])
            send(
                f"📈 Analyzing "
                f"{len(tickers)} stocks..."
            )
            return analyze_multiple(tickers)

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

        # WATCHLIST
        elif text in ('watchlist', '/watchlist'):
            from database import Database
            db = Database()
            watchlist = db.get_watchlist()

            if not watchlist:
                return (
                    "Watchlist is empty. "
                    "Add stocks on dashboard."
                )

            msg = (
                f"📋 YOUR WATCHLIST "
                f"({len(watchlist)} stocks)\n\n"
            )

            sectors = {}
            for w in watchlist:
                sector = w.get('sector', 'other')
                if sector not in sectors:
                    sectors[sector] = []
                sectors[sector].append(w['ticker'])

            for sector, tickers in sectors.items():
                msg += f"{sector}:\n"
                msg += f"  {', '.join(tickers)}\n"

            msg += "\nAdd/remove on dashboard"
            return msg

        # HOLDINGS
        elif text in (
            'holdings', '/holdings', 'mystocks'
        ):
            from database import Database
            from backend.market_data.fetcher import fetch
            from backend.strategies.scanner import (
                scan, calculate_indicators
            )

            db = Database()
            positions = db.get_swing_positions()

            if not positions:
                return (
                    "No active positions tracked.\n"
                    "Add positions on dashboard."
                )

            spy = fetch('SPY', '1y')
            msg = (
                "💼 YOUR POSITIONS\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
            )

            for pos in positions:
                ticker = pos['ticker']
                entry = pos.get('entry_price', 0)
                stop = pos.get('stop_price', 0)
                target1 = pos.get('target1', 0)

                data = fetch(ticker, '1y')
                if not data:
                    continue

                ind = calculate_indicators(data.df)
                current = (
                    ind['close'] if ind else entry
                )
                signal = (
                    scan(ticker, data.df, spy.df)
                    if spy else None
                )

                pnl_pct = (
                    (current - entry) / entry * 100
                ) if entry > 0 else 0

                if current <= stop * 1.02:
                    rec = "⚠️ EXIT — Near stop loss"
                elif current >= target1 * 0.98:
                    rec = "🎯 SELL HALF — Target reached"
                elif (signal and
                      signal.action == 'READY'):
                    rec = "💪 HOLD — Strong setup"
                elif ind and ind['close'] > ind['ema21']:
                    rec = "✅ HOLD — Trend intact"
                else:
                    rec = "⚠️ WATCH — Weakening"

                msg += (
                    f"{ticker}\n"
                    f"Entry: ${entry:.2f} → "
                    f"Now: ${current:.2f}\n"
                    f"PnL: {pnl_pct:+.1f}%\n"
                    f"Stop: ${stop:.2f} | "
                    f"Target: ${target1:.2f}\n"
                    f"👉 {rec}\n\n"
                )

            return msg

        # BUDGET
        elif text in ('budget', '/budget'):
            from dotenv import load_dotenv
            load_dotenv(
                os.path.expanduser('~/sentinel/.env')
            )
            from database import Database
            from backend.portfolio.tracker import (
                PortfolioTracker
            )

            tracker = PortfolioTracker()
            budget = float(
                os.getenv('SWING_BUDGET', '0')
            )
            positions = tracker.get_open_positions()
            deployed = sum(
                p.get('shares', 0) *
                p.get('entry_price', 0)
                for p in positions
            )
            available = max(budget - deployed, 0)

            if budget == 0:
                status = "⚠️ No budget set — scanning only"
            elif available == 0:
                status = "🔴 Budget fully deployed"
            elif available < budget * 0.33:
                status = "🟡 Limited budget remaining"
            else:
                status = "🟢 Budget available"

            return (
                f"💰 BUDGET STATUS\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"Total budget: ${budget:.0f}\n"
                f"Deployed: ${deployed:.2f}\n"
                f"Available: ${available:.2f}\n\n"
                f"Status: {status}\n\n"
                f"Positions: {len(positions)}/3"
            )

        # STATUS
        elif text in ('status', '/status'):
            from backend.execution.broker import (
                get_account, is_market_open
            )

            account = get_account()
            market = is_market_open()

            try:
                import ollama
                ollama.list()
                ai_status = "🟢 Online"
            except Exception:
                ai_status = "🔴 Offline"

            alpaca_status = (
                f"🟢 ${float(account['portfolio_value']):,.0f}"
                if account else "🔴 Offline"
            )

            return (
                f"⚡ SENTINEL STATUS\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"Market: "
                f"{'🟢 OPEN' if market else '🔴 CLOSED'}\n"
                f"Alpaca: {alpaca_status}\n"
                f"AI: {ai_status}\n\n"
                f"Scanning: every 45 min\n"
                f"Morning brief: 9am EST\n"
                f"Exit alerts: every 30 min\n\n"
                f"Dashboard: http://localhost:8501"
            )

        # DISCOVER
        elif text in ('discover', '/discover'):
            send(
                "🔍 Running discovery scan...\n"
                "This takes 2-3 minutes."
            )

            from backend.strategies.discovery import (
                discover_opportunities
            )
            from backend.market_data.fetcher import fetch

            discoveries = discover_opportunities(
                fetch, min_score=70, max_results=5
            )

            if not discoveries:
                return (
                    "No strong discoveries right now."
                )

            msg = "🔍 TOP DISCOVERIES\n\n"
            for d in discoveries:
                emoji = (
                    '🟢' if d.action == 'READY'
                    else '🟡'
                )
                msg += (
                    f"{emoji} {d.ticker} "
                    f"— {d.score}/100\n"
                    f"  {d.reason}\n"
                    f"  RSI: {d.rsi:.0f} | "
                    f"RS: {d.rs_vs_spy:+.1f}%\n\n"
                )

            msg += (
                "\nAdd these on dashboard:\n"
                "http://localhost:8501"
            )
            return msg

        # BOUGHT — record manual buy
        elif (
            text.startswith('bought ') or
            text.startswith('buy ') or
            text.startswith('added ')
        ):
            parts = text.split()

            if len(parts) < 4:
                return (
                    "Format: bought TICKER SHARES PRICE\n"
                    "Example: bought NVDA 0.5 245.50"
                )

            ticker = parts[1].upper()

            try:
                shares = float(parts[2])
                price = float(parts[3])
            except Exception:
                return (
                    "Could not read numbers.\n"
                    "Format: bought NVDA 0.5 245.50"
                )

            stop = round(price * 0.97, 2)
            target1 = round(price * 1.08, 2)
            target2 = round(price * 1.15, 2)
            cost = round(shares * price, 2)

            from backend.portfolio.tracker import (
                PortfolioTracker
            )
            from backend.journal.logger import Journal

            tracker = PortfolioTracker()
            journal = Journal()

            tracker.open_position(
                ticker=ticker,
                shares=shares,
                entry_price=price,
                stop_price=stop,
                target1=target1,
                target2=target2,
                strategy='MANUAL',
                notes='Entered manually via Telegram',
            )

            journal.log_trade_open(
                ticker=ticker,
                strategy='MANUAL',
                shares=shares,
                entry_price=price,
                stop=stop,
                target1=target1,
                target2=target2,
                approved_by='human_manual',
            )

            return (
                f"✅ TRADE RECORDED\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"Stock: {ticker}\n"
                f"Shares: {shares}\n"
                f"Entry: ${price:.2f}\n"
                f"Total: ${cost:.2f}\n\n"
                f"AUTO SET:\n"
                f"Stop loss: ${stop:.2f} (-3%)\n"
                f"Target 1: ${target1:.2f} (+8%)\n"
                f"Target 2: ${target2:.2f} (+15%)\n\n"
                f"Bot will monitor and alert you!\n"
                f"Daily updates at 10am EST"
            )

        # SOLD — record manual sell
        elif (
            text.startswith('sold ') or
            text.startswith('sell ') or
            text.startswith('exited ')
        ):
            parts = text.split()

            if len(parts) < 4:
                return (
                    "Format: sold TICKER SHARES PRICE\n"
                    "Example: sold NVDA 0.25 261.00"
                )

            ticker = parts[1].upper()

            try:
                shares = float(parts[2])
                price = float(parts[3])
            except Exception:
                return (
                    "Could not read numbers.\n"
                    "Format: sold NVDA 0.25 261.00"
                )

            from backend.portfolio.tracker import (
                PortfolioTracker
            )
            from backend.journal.logger import Journal

            tracker = PortfolioTracker()
            journal = Journal()

            result = tracker.close_position(
                ticker, price, 'manual_exit'
            )

            journal.log_trade_close(
                ticker, price, 'manual_exit'
            )

            if result:
                pnl = result.get('pnl', 0)
                pnl_pct = result.get('pnl_pct', 0)
                emoji = '✅' if pnl >= 0 else '❌'

                return (
                    f"{emoji} TRADE CLOSED\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"Stock: {ticker}\n"
                    f"Shares: {shares}\n"
                    f"Exit: ${price:.2f}\n\n"
                    f"RESULT:\n"
                    f"PnL: ${pnl:+.2f}\n"
                    f"Return: {pnl_pct:+.1f}%\n\n"
                    f"{'Great trade! 🎉' if pnl > 0 else 'Take the lesson. Next one. 💪'}"
                )
            else:
                return (
                    f"Could not find open position "
                    f"for {ticker}.\n"
                    f"Check portfolio: text portfolio"
                )

        # HELP
        elif text in (
            'help', '/help', '/start', 'menu'
        ):
            return (
                "⚡ SENTINEL COMMANDS\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "🤖 BOT CONTROLS\n"
                "start — Start the bot\n"
                "stop — Stop the bot\n"
                "pause — Pause (manual mode)\n"
                "resume — Resume (auto mode)\n"
                "restart — Restart bot\n"
                "status — Bot health check\n\n"
                "📡 SCANNING\n"
                "scan — Scan all watchlist stocks\n"
                "top3 — Best 3 right now\n"
                "discover — Find new opportunities\n"
                "watchlist — Your scan list\n\n"
                "📊 ANALYSIS\n"
                "analyze NVDA — Full short+long analysis\n"
                "analyze FSLR NEE ENPH — Mass analysis\n"
                "lt FSLR NEE — Long term focus only\n"
                "scan — Swing opportunities now\n"
                "holdings — Your positions status\n"
                "portfolio — Budget + positions\n"
                "budget — Budget status\n"
                "stats — Performance numbers\n\n"
                "📱 MANUAL TRADES\n"
                "bought NVDA 0.5 245.50 — Record buy\n"
                "sold NVDA 0.25 261.00 — Record sell\n\n"
                "🎯 GOALS\n"
                "goal — Car fund progress\n\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
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
