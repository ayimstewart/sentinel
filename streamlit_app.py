import streamlit as st
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

st.set_page_config(
    page_title='Sentinel',
    page_icon='⚡',
    layout='wide',
    initial_sidebar_state='collapsed',
)

st.markdown("""
<style>
* { font-family: -apple-system, 'Inter', sans-serif; }
.stApp { background-color: #0f0f0f; }
[data-testid="stMetricValue"] {
    font-size: 28px;
    font-weight: 700;
}
[data-testid="stMetricLabel"] {
    font-size: 12px;
    color: #9ca3af;
    text-transform: uppercase;
}
div[data-testid="metric-container"] {
    background: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 8px;
    padding: 16px;
}
.signal-card {
    background: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 8px;
    padding: 16px;
    margin: 8px 0;
}
.ready { color: #22c55e; font-weight: 700; }
.watch { color: #f59e0b; font-weight: 700; }
.avoid { color: #ef4444; font-weight: 700; }
</style>
""", unsafe_allow_html=True)

# ── IMPORTS ──────────────────────────────
from backend.market_data.fetcher import fetch, get_current_price
from backend.strategies.scanner import scan
from backend.portfolio.tracker import PortfolioTracker
from backend.journal.logger import Journal
from backend.configs.symbols import TRADEABLE_ETFS
from backend.risk.engine import evaluate, Portfolio

tracker = PortfolioTracker()
journal = Journal()

# ── TELEGRAM HELPER ──────────────────────
def _send_telegram(message: str):
    import requests
    token = os.getenv('TELEGRAM_BOT_TOKEN', '')
    chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
    if not token or not chat_id:
        return
    requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'HTML',
        },
        timeout=5,
    )

# ── NAVIGATION ───────────────────────────
page = st.sidebar.radio(
    'Navigation',
    [
        '⚡ Today',
        '📊 Positions',
        '📈 Performance',
        '⚙️ Settings',
    ],
    label_visibility='collapsed',
)

st.sidebar.divider()
st.sidebar.caption('SENTINEL v2')
st.sidebar.caption('ETF Swing Trading System')

# ════════════════════════════════════════
# SCREEN 1 — TODAY
# Question: What should I trade right now?
# ════════════════════════════════════════
if page == '⚡ Today':
    st.title('⚡ Today')
    st.caption('What should I trade right now?')

    # Market bar
    try:
        import yfinance as yf
        spy_hist = yf.Ticker('SPY').history(period='2d')
        qqq_hist = yf.Ticker('QQQ').history(period='2d')
        vix_hist = yf.Ticker('^VIX').history(period='2d')

        spy_chg = round(
            (spy_hist['Close'].iloc[-1] - spy_hist['Close'].iloc[-2])
            / spy_hist['Close'].iloc[-2] * 100, 2
        ) if len(spy_hist) >= 2 else 0

        qqq_chg = round(
            (qqq_hist['Close'].iloc[-1] - qqq_hist['Close'].iloc[-2])
            / qqq_hist['Close'].iloc[-2] * 100, 2
        ) if len(qqq_hist) >= 2 else 0

        vix_val = round(
            float(vix_hist['Close'].iloc[-1]), 1
        ) if len(vix_hist) >= 1 else 0

    except Exception:
        spy_chg = qqq_chg = vix_val = 0

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric('SPY', f"{spy_chg:+.1f}%", delta=f"{spy_chg:+.1f}%")
    with col2:
        st.metric('QQQ', f"{qqq_chg:+.1f}%", delta=f"{qqq_chg:+.1f}%")
    with col3:
        st.metric('VIX', f"{vix_val}")
    with col4:
        market = '🟢 BULLISH' if spy_chg > 0 else '🔴 BEARISH'
        st.metric('Market', market)

    st.divider()

    # Scan button
    col1, col2 = st.columns([1, 4])
    with col1:
        scan_now = st.button(
            '🔍 Scan ETFs',
            type='primary',
            use_container_width=True,
        )
    with col2:
        signals = journal.get_todays_signals()
        st.caption(f"Last scan: {len(signals)} signals today")

    # Run scan
    if scan_now:
        with st.spinner(f'Scanning {len(TRADEABLE_ETFS)} ETFs...'):
            try:
                spy_data = fetch('SPY', '1y')
                open_positions = tracker.get_open_positions()
                budget = float(os.getenv('SWING_BUDGET', '300'))

                new_signals = []

                for ticker in TRADEABLE_ETFS:
                    data = fetch(ticker, '1y')
                    if not data or not spy_data:
                        continue

                    signal = scan(ticker, data.df, spy_data.df)
                    if not signal:
                        continue

                    portfolio = Portfolio(
                        positions=open_positions,
                        portfolio_value=budget,
                        cash=budget,
                        daily_pnl=0.0,
                    )
                    risk = evaluate(signal, portfolio)

                    sig_id = journal.log_signal(
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
                    )

                    new_signals.append({
                        'id': sig_id,
                        'ticker': ticker,
                        'strategy': signal.strategy,
                        'action': signal.action,
                        'score': signal.score,
                        'entry': signal.entry,
                        'stop': signal.stop,
                        'target1': signal.target1,
                        'shares': risk.shares,
                        'cost': risk.position_value,
                        'reason': signal.reason,
                        'allowed': risk.allowed,
                        'risk_reason': risk.reason,
                    })

                if new_signals:
                    st.success(f"Found {len(new_signals)} setups!")
                else:
                    st.info(
                        "No setups found. "
                        "Conditions not met today."
                    )

                st.rerun()

            except Exception as e:
                st.error(f"Scan error: {e}")

    # Show today's signals
    signals = journal.get_todays_signals()
    pending = [s for s in signals if s.get('status') == 'pending']

    if not pending:
        st.info("No setups right now. Click Scan ETFs to check.")
    else:
        st.subheader(f"Today's Setups ({len(pending)})")

        for sig in pending:
            action = sig.get('action', 'WATCH')
            color = (
                '🟢' if action == 'READY'
                else '🟡' if action == 'WATCH'
                else '🔴'
            )

            with st.container():
                col1, col2, col3 = st.columns([3, 2, 1])

                with col1:
                    st.markdown(
                        f"### {color} {sig['ticker']} — {action}"
                    )
                    st.write(f"Strategy: {sig.get('strategy')}")
                    score = sig.get('score', 0)
                    st.progress(score / 100)
                    st.caption(f"Score: {score}/100")

                with col2:
                    st.write(
                        f"**Entry:** ${sig.get('entry', 0):.2f}"
                    )
                    st.write(
                        f"**Stop:** ${sig.get('stop', 0):.2f}"
                    )
                    st.write(
                        f"**Target:** "
                        f"${sig.get('target1', 0):.2f} (+8%)"
                    )
                    st.caption(sig.get('reason', ''))

                with col3:
                    ticker = sig.get('ticker')
                    sig_id = sig.get('id')

                    if st.button(
                        '✅ Approve',
                        key=f"app_{sig_id}",
                        type='primary',
                        use_container_width=True,
                    ):
                        journal.approve_signal(sig_id)
                        try:
                            _send_telegram(
                                f"✅ APPROVED: {ticker}\n"
                                f"Entry: ${sig.get('entry', 0):.2f}\n"
                                f"Stop: ${sig.get('stop', 0):.2f}\n"
                                f"Target: ${sig.get('target1', 0):.2f}\n"
                                f"Open Robinhood now!"
                            )
                        except Exception:
                            pass
                        st.success('Approved!')
                        st.rerun()

                    if st.button(
                        '⏭ Skip',
                        key=f"skip_{sig_id}",
                        use_container_width=True,
                    ):
                        journal.skip_signal(sig_id)
                        st.rerun()

                st.divider()

# ════════════════════════════════════════
# SCREEN 2 — POSITIONS
# Question: What do I have open?
# ════════════════════════════════════════
elif page == '📊 Positions':
    st.title('📊 Positions')
    st.caption('What do I have open?')

    positions = tracker.get_open_positions()
    budget = float(os.getenv('SWING_BUDGET', '300'))

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric('Open Positions', f"{len(positions)} / 3")
    with col2:
        total_cost = sum(
            p.get('shares', 0) * p.get('entry_price', 0)
            for p in positions
        )
        st.metric('Deployed', f"${total_cost:.2f}")
    with col3:
        cash = max(budget - total_cost, 0)
        st.metric('Available', f"${cash:.2f}")

    st.divider()

    if not positions:
        st.info(
            "No open positions. "
            "Approve a setup on Today screen."
        )
    else:
        for pos in positions:
            ticker = pos['ticker']

            try:
                current = get_current_price(ticker)
            except Exception:
                current = pos.get('entry_price', 0)

            entry = pos.get('entry_price', 0)
            shares = pos.get('shares', 0)
            stop = pos.get('stop_price', 0)
            target1 = pos.get('target1', 0)

            pnl = (current - entry) * shares
            pnl_pct = (
                (current - entry) / entry * 100
                if entry > 0 else 0
            )

            col1, col2, col3 = st.columns([2, 2, 1])

            with col1:
                st.markdown(f"### {ticker}")
                st.write(
                    f"**Entry:** ${entry:.2f}  |  "
                    f"**Now:** ${current:.2f}"
                )
                st.write(
                    f"**Stop:** ${stop:.2f}  |  "
                    f"**Target:** ${target1:.2f}"
                )
                st.write(
                    f"**Shares:** {shares:.4f}  |  "
                    f"**Strategy:** {pos.get('strategy', '')}"
                )

            with col2:
                st.metric(
                    'P&L',
                    f"${pnl:+.2f}",
                    delta=f"{pnl_pct:+.1f}%",
                )
                if target1 > entry and entry > 0:
                    progress = min(
                        max((current - entry) / (target1 - entry), 0), 1
                    )
                    st.progress(progress)
                    st.caption(
                        f"{progress * 100:.0f}% to target"
                    )

            with col3:
                if st.button(
                    '🚪 Exit',
                    key=f"exit_{ticker}",
                    use_container_width=True,
                ):
                    result = tracker.close_position(
                        ticker, current, 'manual_exit'
                    )
                    if result:
                        journal.log_trade_close(
                            ticker, current, 'manual_exit'
                        )
                        try:
                            _send_telegram(
                                f"🚪 EXIT: {ticker}\n"
                                f"Sell on Robinhood now!\n"
                                f"Price: ${current:.2f}\n"
                                f"PnL: ${pnl:+.2f}"
                            )
                        except Exception:
                            pass
                        st.success('Position closed!')
                        st.rerun()

            st.divider()

    # Add position manually
    st.subheader('Add Position Manually')
    st.caption('After buying on Robinhood')

    with st.form('add_position'):
        col1, col2 = st.columns(2)
        with col1:
            add_ticker = st.selectbox('ETF', TRADEABLE_ETFS)
            add_shares = st.number_input(
                'Shares', min_value=0.01, value=1.0, step=0.01
            )
            add_entry = st.number_input(
                'Entry Price', min_value=0.01, value=100.0
            )
        with col2:
            add_stop = st.number_input(
                'Stop Loss', min_value=0.01, value=97.0
            )
            add_target = st.number_input(
                'Target 1', min_value=0.01, value=108.0
            )
            add_strategy = st.selectbox(
                'Strategy',
                ['EMA_RIDE', 'BREAKOUT', 'RS_TREND'],
            )

        submitted = st.form_submit_button(
            '➕ Add Position',
            type='primary',
            use_container_width=True,
        )

        if submitted:
            tracker.open_position(
                ticker=add_ticker,
                shares=add_shares,
                entry_price=add_entry,
                stop_price=add_stop,
                target1=add_target,
                target2=add_target * 1.07,
                strategy=add_strategy,
            )
            journal.log_trade_open(
                ticker=add_ticker,
                strategy=add_strategy,
                shares=add_shares,
                entry_price=add_entry,
                stop=add_stop,
                target1=add_target,
                target2=add_target * 1.07,
            )
            st.success(f"Added {add_ticker} position!")
            st.rerun()

# ════════════════════════════════════════
# SCREEN 3 — PERFORMANCE
# Question: Is my strategy working?
# ════════════════════════════════════════
elif page == '📈 Performance':
    st.title('📈 Performance')
    st.caption('Is my strategy working?')

    stats = journal.get_stats()
    breakdown = journal.get_strategy_breakdown()

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric('Total Trades', stats.get('total_trades', 0))
    with col2:
        st.metric(
            'Win Rate', f"{stats.get('win_rate', 0):.0f}%"
        )
    with col3:
        st.metric(
            'Total PnL',
            f"${stats.get('total_pnl', 0):+.2f}",
        )
    with col4:
        st.metric(
            'Profit Factor',
            f"{stats.get('profit_factor', 0):.2f}",
        )

    st.divider()

    if breakdown:
        st.subheader('Strategy Breakdown')
        import pandas as pd
        rows = []
        for strat, data in breakdown.items():
            rows.append({
                'Strategy': strat,
                'Trades': data['trades'],
                'Wins': data['wins'],
                'Win Rate': f"{data.get('win_rate', 0):.0f}%",
                'Total PnL': f"${data['total_pnl']:+.2f}",
            })
        if rows:
            st.dataframe(
                pd.DataFrame(rows),
                use_container_width=True,
                hide_index=True,
            )

    st.divider()

    trades = journal.get_closed_trades()
    if trades:
        st.subheader(f'Trade History ({len(trades)})')
        import pandas as pd
        df = pd.DataFrame(trades)
        cols = [
            'ticker', 'strategy',
            'entry_price', 'exit_price',
            'pnl', 'pnl_pct',
            'exit_reason', 'hold_days',
        ]
        show_cols = [c for c in cols if c in df.columns]
        st.dataframe(
            df[show_cols],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info(
            'No completed trades yet. '
            'Approve setups and track results.'
        )

    st.divider()
    st.subheader('🎯 Goal Progress')

    budget = float(os.getenv('SWING_BUDGET', '300'))
    total_pnl = stats.get('total_pnl', 0)
    car_goal = 40000
    saved = budget + total_pnl
    progress = min(saved / car_goal, 1.0)

    st.write(f"**New Car — ${car_goal:,}**")
    st.progress(progress)
    st.write(
        f"${saved:.2f} / ${car_goal:,} "
        f"({progress * 100:.2f}%)"
    )

    weeks_left = int(
        (car_goal - saved) / budget
    ) if budget > 0 else 0
    years = weeks_left // 52
    months = (weeks_left % 52) // 4
    st.caption(
        f"At $300/week: ~{years}y {months}m remaining"
    )

# ════════════════════════════════════════
# SCREEN 4 — SETTINGS
# ════════════════════════════════════════
elif page == '⚙️ Settings':
    st.title('⚙️ Settings')

    st.subheader('System Status')
    col1, col2, col3 = st.columns(3)

    with col1:
        try:
            import ollama
            ollama.list()
            st.success('🟢 Ollama running')
        except Exception:
            st.error('🔴 Ollama offline')

    with col2:
        from backend.execution.broker import get_account
        account = get_account()
        if account:
            st.success('🟢 Alpaca connected')
            st.caption(f"${account['portfolio_value']:,.2f}")
        else:
            st.warning('🟡 Alpaca not connected')

    with col3:
        try:
            from thermal_monitor import thermal
            temp = thermal.get_status()['temp']
            st.success(f'🟢 Mac {temp:.0f}°C')
        except Exception:
            st.info('🔵 No thermal monitor')

    st.divider()

    st.subheader('Budget')
    budget = float(os.getenv('SWING_BUDGET', '300'))
    st.metric('Weekly Budget', f'${budget:.0f}')
    st.caption('Edit SWING_BUDGET in ~/sentinel/.env')

    st.divider()

    st.subheader('ETF Universe')
    for etf in TRADEABLE_ETFS:
        st.write(f"• {etf}")

    st.divider()

    st.subheader('Decision Log Today')
    rejections = journal.get_todays_rejections()
    signals = journal.get_todays_signals()

    col1, col2 = st.columns(2)
    with col1:
        st.metric('Signals today', len(signals))
    with col2:
        st.metric('Rejections today', len(rejections))

    if rejections:
        st.write('**Recent rejections:**')
        for r in rejections[:5]:
            st.caption(f"{r['ticker']}: {r['reason']}")
