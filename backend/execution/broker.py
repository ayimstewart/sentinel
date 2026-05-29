import os
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class OrderResult:
    success: bool
    order_id: str
    ticker: str
    side: str
    shares: float
    price: float
    status: str
    reason: str = ''


def get_client():
    try:
        from alpaca.trading.client import TradingClient
        key = os.getenv('ALPACA_API_KEY', '')
        secret = os.getenv('ALPACA_SECRET_KEY', '')
        paper = (
            os.getenv('ALPACA_PAPER', 'true').lower() == 'true'
        )

        if not key or not secret:
            logger.warning('Alpaca keys missing')
            return None

        return TradingClient(key, secret, paper=paper)
    except Exception as e:
        logger.error(f"Alpaca client error: {e}")
        return None


def get_account() -> Optional[dict]:
    client = get_client()
    if not client:
        return None
    try:
        account = client.get_account()
        return {
            'status': account.status,
            'portfolio_value': float(account.portfolio_value),
            'cash': float(account.cash),
            'buying_power': float(account.buying_power),
            'trading_blocked': account.trading_blocked,
        }
    except Exception as e:
        logger.error(f"Account fetch error: {e}")
        return None


def place_buy(
    ticker: str,
    shares: float,
    note: str = '',
) -> OrderResult:
    client = get_client()
    if not client:
        return OrderResult(
            success=False,
            order_id='',
            ticker=ticker,
            side='buy',
            shares=shares,
            price=0.0,
            status='failed',
            reason='Alpaca not connected',
        )

    for attempt in range(3):
        try:
            from alpaca.trading.requests import MarketOrderRequest
            from alpaca.trading.enums import OrderSide, TimeInForce

            order = client.submit_order(
                MarketOrderRequest(
                    symbol=ticker,
                    qty=shares,
                    side=OrderSide.BUY,
                    time_in_force=TimeInForce.DAY,
                )
            )

            logger.info(
                f"BUY order placed: {ticker} "
                f"{shares} shares (attempt {attempt + 1})"
            )

            return OrderResult(
                success=True,
                order_id=str(order.id),
                ticker=ticker,
                side='buy',
                shares=shares,
                price=float(order.filled_avg_price or 0),
                status=str(order.status),
                reason=note,
            )

        except Exception as e:
            logger.warning(
                f"Buy attempt {attempt + 1} failed: {e}"
            )
            if attempt < 2:
                import time
                time.sleep(2)

    return OrderResult(
        success=False,
        order_id='',
        ticker=ticker,
        side='buy',
        shares=shares,
        price=0.0,
        status='failed',
        reason='All attempts failed',
    )


def place_sell(
    ticker: str,
    shares: float,
    note: str = '',
) -> OrderResult:
    client = get_client()
    if not client:
        return OrderResult(
            success=False,
            order_id='',
            ticker=ticker,
            side='sell',
            shares=shares,
            price=0.0,
            status='failed',
            reason='Alpaca not connected',
        )

    for attempt in range(3):
        try:
            from alpaca.trading.requests import MarketOrderRequest
            from alpaca.trading.enums import OrderSide, TimeInForce

            order = client.submit_order(
                MarketOrderRequest(
                    symbol=ticker,
                    qty=shares,
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY,
                )
            )

            logger.info(
                f"SELL order placed: {ticker} "
                f"{shares} shares (attempt {attempt + 1})"
            )

            return OrderResult(
                success=True,
                order_id=str(order.id),
                ticker=ticker,
                side='sell',
                shares=shares,
                price=float(order.filled_avg_price or 0),
                status=str(order.status),
                reason=note,
            )

        except Exception as e:
            logger.warning(
                f"Sell attempt {attempt + 1} failed: {e}"
            )
            if attempt < 2:
                import time
                time.sleep(2)

    return OrderResult(
        success=False,
        order_id='',
        ticker=ticker,
        side='sell',
        shares=shares,
        price=0.0,
        status='failed',
        reason='All attempts failed',
    )


def get_positions() -> list:
    client = get_client()
    if not client:
        return []
    try:
        positions = client.get_all_positions()
        return [
            {
                'ticker': p.symbol,
                'shares': float(p.qty),
                'entry_price': float(p.avg_entry_price),
                'current_price': float(p.current_price or 0),
                'pnl': float(p.unrealized_pl or 0),
                'pnl_pct': float(p.unrealized_plpc or 0) * 100,
                'market_value': float(p.market_value or 0),
            }
            for p in positions
        ]
    except Exception as e:
        logger.error(f"Positions fetch error: {e}")
        return []


def is_market_open() -> bool:
    client = get_client()
    if not client:
        import pytz
        from datetime import datetime
        est = pytz.timezone('US/Eastern')
        now = datetime.now(est)
        if now.weekday() >= 5:
            return False
        open_time = now.replace(hour=9, minute=30, second=0)
        close_time = now.replace(hour=16, minute=0, second=0)
        return open_time <= now <= close_time

    try:
        clock = client.get_clock()
        return clock.is_open
    except Exception as e:
        logger.error(f"Clock error: {e}")
        return False


def get_portfolio_value() -> float:
    account = get_account()
    if account:
        return account['portfolio_value']
    return float(os.getenv('SWING_BUDGET', '300'))
