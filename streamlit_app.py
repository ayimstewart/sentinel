import streamlit as st
import sys
import os
import subprocess

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv(os.path.expanduser('~/sentinel/.env'))

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
</style>
""", unsafe_allow_html=True)

# ── IMPORTS ──────────────────────────────
from backend.market_data.fetcher import (
    fetch, get_current_price
)
from backend.strategies.scanner import (
    scan, calculate_indicators
)
from backend.portfolio.tracker import PortfolioTracker
from backend.journal.logger import Journal
from backend.risk.engine import evaluate, Portfolio
from database import Database

tracker = PortfolioTracker()
journal = Journal()


def tradingview_link(ticker):
    return (
        f"https://www.tradingview.com/chart/"
        f"?symbol={ticker}"
    )


def _send_telegram(message: str):
    import requests
    token = os.getenv('TELEGRAM_BOT_TOKEN', '')
    chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
    if not token or not chat_id:
        return
    try:
        requests.post(
            f"https://api.telegram.org/"
            f"bot{token}/sendMessage",
            json={
                'chat_id': chat_id,
                'text': message,
                'parse_mode': 'HTML',
            },
            timeout=5,
        )
    except Exception:
        pass


def _is_bot_running() -> bool:
    try:
        result = subprocess.run(
            ['pgrep', '-f', 'main.py'],
            capture_output=True,
        )
        return result.returncode == 0
    except Exception:
        return False


# ── NAVIGATION ───────────────────────────
page = st.sidebar.radio(
    'Navigation',
    [
        '⚡ Today',
        '📊 Portfolio',
        '📈 Stats',
        '💬 Assistant',
        '⚙️ Settings',
    ],
    label_visibility='collapsed',
)

st.sidebar.divider()
st.sidebar.caption('SENTINEL v2')
st.sidebar.caption('Swing Trading System')

# ════════════════════════════════════════
# PAGE 1 — TODAY
# ════════════════════════════════════════
if page == '⚡ Today':
    st.title('⚡ Today')
    st.caption('What should I trade right now?')

    # Market bar
    try:
        import yfinance as yf
        spy_hist = yf.Ticker('SPY').history(period='2d')
        spy_chg = round(
            (spy_hist['Close'].iloc[-1] -
             spy_hist['Close'].iloc[-2]) /
            spy_hist['Close'].iloc[-2] * 100, 2
        ) if len(spy_hist) >= 2 else 0
    except Exception:
        spy_chg = 0

    try:
        from main import get_capital_status
        capital = get_capital_status()
    except Exception:
        capital = {
            'available': 0,
            'positions': 0,
            'capital_full': False,
        }

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric('SPY', f"{spy_chg:+.1f}%")
    with col2:
        st.metric(
            'Available',
            f"${capital['available']:.0f}"
        )
    with col3:
        st.metric(
            'Positions',
            f"{capital['positions']}/3"
        )

    st.divider()

    if capital.get('capital_full'):
        st.warning(
            "💰 Capital fully deployed — "
            "no new trades until exits free up cash"
        )

    if st.button(
        '🔍 Scan Now',
        type='primary',
        use_container_width=True,
    ):
        with st.spinner('Scanning...'):
            try:
                from main import run_scan
                run_scan()
                st.rerun()
            except Exception as e:
                st.error(f"Scan error: {e}")

    # Today's signals
    signals = journal.get_todays_signals()
    pending = [
        s for s in signals
        if s.get('status') == 'pending'
    ]

    if not pending:
        st.info("No signals yet. Click Scan Now.")
    else:
        st.subheader(f"Today's Setups ({len(pending)})")

        for sig in pending:
            state = sig.get('action', 'WATCH')
            ticker = sig.get('ticker', '')

            emoji = (
                '🟢' if state == 'BUY_ZONE'
                else '🟡' if state == 'WATCH'
                else '⏳'
            )

            with st.container():
                col1, col2 = st.columns([3, 1])

                with col1:
                    st.markdown(
                        f"### {emoji} {ticker}"
                    )
                    entry = sig.get('entry', 0)
                    stop = sig.get('stop', 0)
                    t1 = sig.get('target1', 0)
                    hold = sig.get('hold_days', 12)
                    zone = sig.get(
                        'entry_zone_high', entry
                    )

                    if state == 'BUY_ZONE':
                        st.write(
                            f"Buy at ${entry:.2f} · "
                            f"Stop ${stop:.2f} · "
                            f"Sell ${t1:.2f} · "
                            f"Hold {hold} days"
                        )
                    elif state == 'WATCH':
                        st.write(
                            f"Watch below ${zone:.2f} · "
                            f"Target ${t1:.2f} · "
                            f"Hold {hold} days"
                        )
                    else:
                        st.write(
                            f"Too extended — "
                            f"wait for ${zone:.2f}"
                        )

                    st.caption(sig.get('reason', ''))
                    st.markdown(
                        f"[📈 TradingView]"
                        f"({tradingview_link(ticker)})"
                    )

                with col2:
                    sig_id = sig.get('id')
                    if state == 'BUY_ZONE':
                        if st.button(
                            '✅ Buy',
                            key=f"app_{sig_id}",
                            type='primary',
                            use_container_width=True,
                        ):
                            try:
                                from main import (
                                    execute_approved_trade
                                )
                                execute_approved_trade(sig)
                            except Exception:
                                pass
                            journal.approve_signal(sig_id)
                            st.success('✅ Trade placed!')
                            st.rerun()

                    if st.button(
                        '⏭ Skip',
                        key=f"skip_{sig_id}",
                        use_container_width=True,
                    ):
                        journal.skip_signal(sig_id)
                        st.rerun()

                st.divider()

    # ETF Rankings
    st.divider()
    with st.expander('📊 ETF Rankings', expanded=False):
        if st.button('🏆 Rank All ETFs', key='rank_btn'):
            with st.spinner('Ranking ETFs...'):
                try:
                    from backend.strategies.ranker import (
                        run_ranking
                    )
                    import pandas as pd

                    all_ranks, top3 = run_ranking(fetch)

                    if top3:
                        for i, rank in enumerate(top3):
                            col1, col2 = st.columns([3, 2])
                            with col1:
                                r_emoji = (
                                    '🟢'
                                    if rank.action in (
                                        'READY', 'BUY_ZONE'
                                    )
                                    else '🟡'
                                )
                                st.markdown(
                                    f"### {i+1}. "
                                    f"{r_emoji} {rank.ticker}"
                                )
                                st.progress(
                                    rank.composite_score / 100
                                )
                                st.caption(
                                    f"Score: "
                                    f"{rank.composite_score}/100"
                                )
                            with col2:
                                st.write(
                                    f"Trend: "
                                    f"{rank.trend_score:.0f}"
                                )
                                st.write(
                                    f"RS: {rank.rs_score:.0f}"
                                )
                                st.write(
                                    f"RSI: {rank.rsi:.0f}"
                                )
                            st.divider()
                    else:
                        st.info("No top picks today.")

                    if all_ranks:
                        rows = []
                        for r in all_ranks[:20]:
                            rows.append({
                                'Ticker': r.ticker,
                                'Score': r.composite_score,
                                'RS': r.rs_score,
                                'RSI': round(r.rsi, 0),
                                'Action': r.action,
                            })
                        st.dataframe(
                            pd.DataFrame(rows),
                            use_container_width=True,
                            hide_index=True,
                        )

                except Exception as e:
                    st.error(f"Ranking error: {e}")

    # Discover
    st.divider()
    with st.expander(
        '🔍 Discover Opportunities', expanded=False
    ):
        col1, col2 = st.columns(2)
        with col1:
            min_score = st.slider(
                'Min score', 50, 90, 70,
                key='discover_min'
            )
        with col2:
            max_results = st.slider(
                'Max results', 5, 20, 10,
                key='discover_max'
            )

        if st.button(
            '🔍 Discover Now',
            key='discover_btn',
            use_container_width=True,
        ):
            with st.spinner('Scanning universe...'):
                try:
                    from backend.strategies.discovery import (
                        discover_opportunities,
                        DISCOVERY_UNIVERSE,
                    )
                    discoveries = discover_opportunities(
                        fetch,
                        min_score=min_score,
                        max_results=max_results,
                    )

                    if not discoveries:
                        st.info(
                            'No discoveries. '
                            'Try lower score.'
                        )
                    else:
                        st.success(
                            f'{len(discoveries)} found!'
                        )
                        existing = [
                            w['ticker']
                            for w in db.get_watchlist()
                        ]
                        for d in discoveries:
                            col1, col2, col3 = (
                                st.columns([2, 2, 1])
                            )
                            with col1:
                                d_emoji = (
                                    '🟢'
                                    if d.action in (
                                        'READY', 'BUY_ZONE'
                                    )
                                    else '🟡'
                                )
                                st.markdown(
                                    f"**{d_emoji} {d.ticker}**"
                                )
                                st.progress(d.score / 100)
                                st.caption(
                                    f"{d.score}/100 · "
                                    f"{d.sector}"
                                )
                            with col2:
                                st.write(
                                    f"RS: "
                                    f"{d.rs_vs_spy:+.1f}%"
                                )
                                st.write(
                                    f"Vol: "
                                    f"{d.volume_ratio:.1f}x"
                                )
                                st.write(
                                    f"RSI: {d.rsi:.0f}"
                                )
                            with col3:
                                if d.ticker in existing:
                                    st.success('✅')
                                else:
                                    if st.button(
                                        '➕',
                                        key=f"disc_{d.ticker}",
                                        use_container_width=True,
                                    ):
                                        db.add_to_watchlist(
                                            d.ticker,
                                            'stock',
                                            d.sector,
                                            d.reason,
                                        )
                                        st.rerun()
                            st.caption(d.reason)
                            st.divider()

                except Exception as e:
                    st.error(f"Discovery error: {e}")

# ════════════════════════════════════════
# PAGE 2 — PORTFOLIO
# ════════════════════════════════════════
elif page == '📊 Portfolio':
    st.title('📊 Portfolio')

    tab1, tab2, tab3 = st.tabs([
        '📈 Active Trades',
        '🏦 ETF Holdings',
        '📋 Watchlist',
    ])

    # ── TAB 1: ACTIVE TRADES ─────────────
    with tab1:
        positions = tracker.get_open_positions()
        budget = float(os.getenv('SWING_BUDGET', '300'))
        total_cost = sum(
            p.get('shares', 0) * p.get('entry_price', 0)
            for p in positions
        )
        available = max(budget - total_cost, 0)

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric(
                'Positions', f"{len(positions)} / 3"
            )
        with col2:
            st.metric('Deployed', f"${total_cost:.2f}")
        with col3:
            st.metric('Available', f"${available:.2f}")

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
                        f"**Strategy:** "
                        f"{pos.get('strategy', '')}"
                    )
                    st.markdown(
                        f"[📈 TradingView]"
                        f"({tradingview_link(ticker)})"
                    )

                with col2:
                    st.metric(
                        'P&L',
                        f"${pnl:+.2f}",
                        delta=f"{pnl_pct:+.1f}%",
                    )
                    if target1 > entry and entry > 0:
                        progress = min(
                            max(
                                (current - entry) /
                                (target1 - entry), 0
                            ), 1
                        )
                        st.progress(progress)
                        st.caption(
                            f"{progress * 100:.0f}%"
                            f" to target"
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
                                ticker, current,
                                'manual_exit'
                            )
                            _send_telegram(
                                f"🚪 EXIT: {ticker}\n"
                                f"Price: ${current:.2f}\n"
                                f"PnL: ${pnl:+.2f}"
                            )
                            st.success('Closed!')
                            st.rerun()

                st.divider()

        # Add position manually
        st.subheader('Add Position Manually')
        st.caption('After buying on Robinhood')

        with st.form('add_position'):
            col1, col2 = st.columns(2)
            with col1:
                add_ticker = st.text_input(
                    'Ticker', placeholder='e.g. NVDA'
                ).upper()
                add_shares = st.number_input(
                    'Shares',
                    min_value=0.0001,
                    value=1.0,
                    step=0.01,
                    format="%.4f",
                )
                add_entry = st.number_input(
                    'Entry Price',
                    min_value=0.01,
                    value=100.0,
                )
            with col2:
                add_stop = st.number_input(
                    'Stop Loss',
                    min_value=0.01,
                    value=97.0,
                )
                add_target = st.number_input(
                    'Target 1',
                    min_value=0.01,
                    value=108.0,
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

            if submitted and add_ticker:
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
                st.success(f"Added {add_ticker}!")
                st.rerun()

    # ── TAB 2: ETF HOLDINGS ──────────────
    with tab2:
        st.subheader('ETF Long Term Holdings')
        st.caption(
            'Track your long-term ETF portfolio'
        )

        db2 = Database()

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            etf_ticker = st.text_input(
                'ETF ticker', placeholder='e.g. VOO'
            ).upper()
        with col2:
            etf_shares = st.number_input(
                'Shares', min_value=0.0,
                value=0.0, step=0.001, format="%.4f",
                key='etf_shares_input',
            )
        with col3:
            etf_cost = st.number_input(
                'Avg cost', min_value=0.0, value=0.0,
                key='etf_cost_input',
            )
        with col4:
            st.write("")
            st.write("")
            if st.button(
                '➕ Add ETF', use_container_width=True
            ):
                if etf_ticker:
                    db2.add_etf_holding(
                        etf_ticker, etf_shares, etf_cost
                    )
                    st.success(f"Added {etf_ticker}!")
                    st.rerun()

        st.divider()

        holdings = db2.get_etf_holdings()
        if not holdings:
            st.info('No ETF holdings tracked yet.')
        else:
            total_etf_value = 0.0
            for h in holdings:
                ticker = h['ticker']
                shares = h.get('shares', 0)
                avg_cost = h.get('avg_cost', 0)
                try:
                    current = get_current_price(ticker)
                except Exception:
                    current = avg_cost

                value = shares * current
                cost_basis = shares * avg_cost
                pnl = value - cost_basis
                pnl_pct = (
                    pnl / cost_basis * 100
                ) if cost_basis > 0 else 0
                total_etf_value += value

                col1, col2, col3, col4 = (
                    st.columns([2, 2, 2, 1])
                )
                with col1:
                    st.write(f"**{ticker}**")
                    st.caption(f"{shares:.4f} shares")
                with col2:
                    st.write(f"Now: ${current:.2f}")
                    st.caption(f"Avg: ${avg_cost:.2f}")
                with col3:
                    st.write(f"${value:.2f} total")
                    st.caption(
                        f"PnL: ${pnl:+.2f} "
                        f"({pnl_pct:+.1f}%)"
                    )
                with col4:
                    if st.button(
                        '🗑️',
                        key=f"del_etf_{ticker}",
                        use_container_width=True,
                    ):
                        db2.remove_etf_holding(ticker)
                        st.rerun()

                st.divider()

            st.metric(
                'Total ETF Value',
                f"${total_etf_value:,.2f}"
            )

    # ── TAB 3: WATCHLIST ─────────────────
    with tab3:
        st.subheader('Swing Stock Watchlist')
        st.caption(
            'These stocks are scanned daily '
            'for opportunities'
        )

        db3 = Database()

        col1, col2, col3 = st.columns([2, 2, 1])
        with col1:
            new_ticker = st.text_input(
                'Add ticker', placeholder='e.g. AMD'
            ).upper()
        with col2:
            new_sector = st.selectbox(
                'Sector',
                ['ai_tech', 'semiconductors',
                 'cybersecurity', 'software',
                 'fintech', 'space', 'biotech',
                 'consumer_tech', 'utilities',
                 'social_media', 'speculative',
                 'other'],
            )
        with col3:
            st.write("")
            st.write("")
            if st.button(
                '➕ Add',
                type='primary',
                use_container_width=True,
                key='wl_add',
            ):
                if new_ticker:
                    ok = db3.add_to_watchlist(
                        new_ticker, 'stock', new_sector
                    )
                    if ok:
                        st.success(f"Added {new_ticker}!")
                        st.rerun()
                    else:
                        st.error('Failed to add')

        st.divider()

        wl = db3.get_watchlist()
        stocks = [
            w for w in wl
            if w['ticker_type'] == 'stock'
        ]
        st.write(
            f"**{len(stocks)} stocks being scanned**"
        )

        for stock in stocks:
            col1, col2, col3 = st.columns([2, 3, 1])
            with col1:
                st.write(f"**{stock['ticker']}**")
            with col2:
                st.write(
                    f"{stock['sector']} · "
                    f"added {stock['added_at'][:10]}"
                )
            with col3:
                if st.button(
                    '🗑️',
                    key=f"del_wl_{stock['ticker']}",
                    use_container_width=True,
                ):
                    db3.remove_from_watchlist(
                        stock['ticker']
                    )
                    st.rerun()

# ════════════════════════════════════════
# PAGE 3 — STATS
# ════════════════════════════════════════
elif page == '📈 Stats':
    st.title('📈 Stats')

    tab1, tab2, tab3 = st.tabs([
        '📊 Performance',
        '🧪 Backtest',
        '🎯 Goal',
    ])

    # ── TAB 1: PERFORMANCE ───────────────
    with tab1:
        stats = journal.get_stats()
        breakdown = journal.get_strategy_breakdown()

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric(
                'Total Trades',
                stats.get('total_trades', 0)
            )
        with col2:
            st.metric(
                'Win Rate',
                f"{stats.get('win_rate', 0):.0f}%"
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
                    'Win Rate': (
                        f"{data.get('win_rate', 0):.0f}%"
                    ),
                    'PnL': (
                        f"${data['total_pnl']:+.2f}"
                    ),
                })
            st.dataframe(
                pd.DataFrame(rows),
                use_container_width=True,
                hide_index=True,
            )

        st.divider()

        trades = journal.get_closed_trades()
        if trades:
            st.subheader(
                f'Trade History ({len(trades)})'
            )
            import pandas as pd
            df = pd.DataFrame(trades)
            cols = [
                'ticker', 'strategy',
                'entry_price', 'exit_price',
                'pnl', 'pnl_pct',
                'exit_reason', 'hold_days',
            ]
            show_cols = [
                c for c in cols if c in df.columns
            ]
            st.dataframe(
                df[show_cols],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info(
                'No completed trades yet.'
            )

    # ── TAB 2: BACKTEST ──────────────────
    with tab2:
        st.caption('Test strategies on historical data')

        col1, col2, col3 = st.columns(3)
        with col1:
            bt_ticker = st.selectbox(
                'Ticker',
                ['SMH', 'XLK', 'CIBR', 'VUG',
                 'URA', 'IWM', 'XLV', 'GLD',
                 'XLE', 'XLF', 'NVDA', 'AAPL'],
            )
        with col2:
            bt_strategy = st.selectbox(
                'Strategy',
                ['ALL', 'EMA_RIDE',
                 'BREAKOUT', 'RS_TREND'],
            )
        with col3:
            bt_capital = st.number_input(
                'Starting Capital',
                min_value=100,
                value=300,
                step=100,
            )

        if st.button(
            '▶ Run Backtest',
            type='primary',
            use_container_width=True,
        ):
            with st.spinner(
                f'Backtesting {bt_ticker}...'
            ):
                try:
                    from backend.backtest.engine import (
                        BacktestEngine
                    )
                    df = fetch(bt_ticker, '2y')
                    spy_df = fetch('SPY', '2y')

                    if not df or not spy_df:
                        st.error('Could not fetch data')
                    else:
                        engine = BacktestEngine(
                            initial_capital=bt_capital
                        )
                        result = engine.run(
                            bt_ticker,
                            df.df, spy_df.df,
                            bt_strategy,
                        )

                        if not result:
                            st.warning('No trades found')
                        else:
                            c1, c2, c3, c4 = (
                                st.columns(4)
                            )
                            with c1:
                                st.metric(
                                    'Win Rate',
                                    f"{result.win_rate}%"
                                )
                                st.metric(
                                    'Trades',
                                    result.total_trades
                                )
                            with c2:
                                st.metric(
                                    'Return',
                                    f"{result.total_return_pct}%"
                                )
                                st.metric(
                                    'Final Value',
                                    f"${result.final_value}"
                                )
                            with c3:
                                st.metric(
                                    'Profit Factor',
                                    result.profit_factor
                                )
                                st.metric(
                                    'Sharpe',
                                    result.sharpe_ratio
                                )
                            with c4:
                                st.metric(
                                    'Max Drawdown',
                                    f"-{result.max_drawdown_pct}%"
                                )
                                st.metric(
                                    'Expectancy',
                                    f"${result.expectancy}"
                                )

                            st.divider()
                            if result.win_rate >= 55 and \
                                    result.profit_factor >= 1.5:
                                st.success(
                                    '✅ Strategy viable!'
                                )
                            elif result.profit_factor >= 1.0:
                                st.warning(
                                    '⚠️ Marginal edge.'
                                )
                            else:
                                st.error(
                                    '❌ No edge detected.'
                                )

                            if result.trades:
                                st.divider()
                                import pandas as pd
                                rows = [{
                                    'Entry': t.entry_date,
                                    'Exit': t.exit_date,
                                    'Entry $': t.entry_price,
                                    'Exit $': t.exit_price,
                                    'PnL': t.pnl,
                                    'Days': t.hold_days,
                                } for t in result.trades]
                                st.dataframe(
                                    pd.DataFrame(rows),
                                    use_container_width=True,
                                    hide_index=True,
                                )

                except Exception as e:
                    st.error(f"Backtest error: {e}")
                    import traceback
                    st.code(traceback.format_exc())

    # ── TAB 3: GOAL ──────────────────────
    with tab3:
        stats = journal.get_stats()
        budget = float(os.getenv('SWING_BUDGET', '300'))
        total_pnl = stats.get('total_pnl', 0)
        car_goal = 40000
        saved = budget + total_pnl
        progress = min(saved / car_goal, 1.0)
        weeks_left = int(
            (car_goal - saved) / budget
        ) if budget > 0 else 0
        years = weeks_left // 52
        months = (weeks_left % 52) // 4

        st.subheader('🎯 New Car — $40,000')
        st.progress(progress)

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric('Saved', f"${saved:,.2f}")
        with col2:
            st.metric(
                'Progress',
                f"{progress * 100:.1f}%"
            )
        with col3:
            st.metric(
                'Timeline',
                f"~{years}y {months}m"
            )

        st.divider()
        st.write(
            f"At ${budget:.0f}/week: "
            f"**{weeks_left} weeks remaining**"
        )
        st.caption(
            f"Total PnL from trading: "
            f"${total_pnl:+.2f}"
        )

# ════════════════════════════════════════
# PAGE 4 — ASSISTANT
# ════════════════════════════════════════
elif page == '💬 Assistant':
    st.title('💬 Assistant')
    st.caption('Ask Sentinel anything')

    # Quick action buttons
    cols = st.columns(4)
    quick_cmd = None
    with cols[0]:
        if st.button(
            '📡 Scan', use_container_width=True
        ):
            quick_cmd = 'scan'
    with cols[1]:
        if st.button(
            '🏆 Top 3', use_container_width=True
        ):
            quick_cmd = 'top3'
    with cols[2]:
        if st.button(
            '💼 Portfolio', use_container_width=True
        ):
            quick_cmd = 'portfolio'
    with cols[3]:
        if st.button(
            '📊 Stats', use_container_width=True
        ):
            quick_cmd = 'stats'

    # Chat history
    if 'messages' not in st.session_state:
        st.session_state.messages = []

    # Process quick button click
    if quick_cmd:
        st.session_state.messages.append({
            'role': 'user',
            'content': quick_cmd,
        })
        try:
            from backend.telegram.handler import (
                handle_command
            )
            response = handle_command(quick_cmd)
        except Exception as e:
            response = f"Error: {e}"
        st.session_state.messages.append({
            'role': 'assistant',
            'content': response,
        })
        st.rerun()

    # Display messages
    for msg in st.session_state.messages[-20:]:
        with st.chat_message(msg['role']):
            content = msg['content']

            # Mass analysis: multiple stocks separated by === lines
            if '=' * 10 in content and \
               content.count('SHORT TERM') > 1:

                stocks = content.split('=' * 35)
                stocks = [s.strip() for s in stocks
                          if s.strip() and '$' in s]

                for stock_result in stocks:
                    lines = stock_result.split('\n')
                    ticker_line = lines[0] if lines else ''
                    ticker = ticker_line.replace(
                        '📊', ''
                    ).strip()

                    with st.expander(
                        f"📊 {ticker}",
                        expanded=False
                    ):
                        st.text(stock_result)
            else:
                st.write(content)

    # Chat input
    if prompt := st.chat_input(
        'Ask anything… (try: help, scan, '
        'analyze NVDA, goal)'
    ):
        st.session_state.messages.append({
            'role': 'user',
            'content': prompt,
        })
        try:
            from backend.telegram.handler import (
                handle_command
            )
            response = handle_command(prompt)
        except Exception as e:
            response = f"Error: {e}"
        st.session_state.messages.append({
            'role': 'assistant',
            'content': response,
        })
        st.rerun()

# ════════════════════════════════════════
# PAGE 5 — SETTINGS
# ════════════════════════════════════════
elif page == '⚙️ Settings':
    st.title('⚙️ Settings')

    # 1. BUDGET
    st.subheader('💰 Budget')
    budget_val = float(os.getenv('SWING_BUDGET', '300'))
    new_budget = st.number_input(
        'Weekly swing budget ($)',
        min_value=0,
        value=int(budget_val),
        step=50,
    )
    if st.button('💾 Save Budget'):
        env_path = os.path.expanduser('~/sentinel/.env')
        try:
            lines = []
            updated = False
            if os.path.exists(env_path):
                with open(env_path, 'r') as f:
                    for line in f:
                        if line.startswith(
                            'SWING_BUDGET='
                        ):
                            lines.append(
                                f'SWING_BUDGET='
                                f'{new_budget}\n'
                            )
                            updated = True
                        else:
                            lines.append(line)
            if not updated:
                lines.append(
                    f'SWING_BUDGET={new_budget}\n'
                )
            with open(env_path, 'w') as f:
                f.writelines(lines)
            st.success(
                f'Budget saved: ${new_budget}'
            )
        except Exception as e:
            st.error(f'Save failed: {e}')

    st.divider()

    # 2. BOT STATUS
    st.subheader('⚡ Bot Status')
    bot_running = _is_bot_running()

    if bot_running:
        st.success('🟢 Bot is RUNNING')
    else:
        st.error('🔴 Bot is STOPPED')

    try:
        last_signals = journal.get_todays_signals()
        if last_signals:
            last_ts = last_signals[-1].get(
                'created_at', 'unknown'
            )
            st.caption(f"Last scan: {last_ts[:16]}")
    except Exception:
        pass

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button(
            '▶ Start Bot',
            use_container_width=True,
            disabled=bot_running,
        ):
            try:
                subprocess.Popen(
                    ['python3.11', 'main.py'],
                    cwd=os.path.expanduser(
                        '~/sentinel'
                    ),
                )
                st.success('Bot starting…')
                st.rerun()
            except Exception as e:
                st.error(f'Start failed: {e}')
    with col2:
        if st.button(
            '⏹ Stop Bot',
            use_container_width=True,
            disabled=not bot_running,
        ):
            subprocess.run(
                ['pkill', '-f', 'main.py'],
                capture_output=True,
            )
            st.success('Bot stopped')
            st.rerun()
    with col3:
        if st.button(
            '🔄 Restart',
            use_container_width=True,
        ):
            subprocess.run(
                ['pkill', '-f', 'main.py'],
                capture_output=True,
            )
            import time; time.sleep(2)
            subprocess.Popen(
                ['python3.11', 'main.py'],
                cwd=os.path.expanduser('~/sentinel'),
            )
            st.success('Bot restarting…')
            st.rerun()

    st.divider()

    # 3. SYSTEM
    st.subheader('🔌 System Status')
    col1, col2, col3 = st.columns(3)

    with col1:
        try:
            from backend.execution.broker import (
                get_account
            )
            account = get_account()
            if account:
                st.success('🟢 Alpaca connected')
                st.caption(
                    f"${account['portfolio_value']:,.2f}"
                )
            else:
                st.warning('🟡 Alpaca offline')
        except Exception:
            st.warning('🟡 Alpaca offline')

    with col2:
        try:
            import ollama
            ollama.list()
            st.success('🟢 Ollama running')
        except Exception:
            st.error('🔴 Ollama offline')

    with col3:
        token = os.getenv('TELEGRAM_BOT_TOKEN', '')
        if token:
            st.success('🟢 Telegram configured')
        else:
            st.warning('🟡 Telegram not set')

    st.divider()

    # 4. THERMAL
    st.subheader('🌡️ Thermal')
    try:
        from thermal_monitor import thermal
        status = thermal.get_status()
        temp = status.get('temp', 0)
        state = status.get('state', 'unknown')
        col1, col2 = st.columns(2)
        with col1:
            st.metric('Temperature', f"{temp:.0f}°C")
        with col2:
            st.metric('State', state)
    except Exception:
        st.info('No thermal monitor available')

    st.divider()

    # 5. DANGER ZONE
    st.subheader('🚨 Danger Zone')
    st.caption('These actions affect all processes')

    col1, col2 = st.columns(2)
    with col1:
        if st.button(
            '🛑 Emergency Stop All',
            type='primary',
            use_container_width=True,
        ):
            subprocess.run(
                ['pkill', '-f', 'main.py'],
                capture_output=True,
            )
            subprocess.run(
                ['pkill', '-f', 'sentinel_telegram'],
                capture_output=True,
            )
            st.warning('All processes stopped')
    with col2:
        st.write("")
        rejections = journal.get_todays_rejections()
        st.caption(
            f"Rejections today: {len(rejections)}"
        )
