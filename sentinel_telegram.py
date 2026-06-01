import os
import sys
import time
import logging
import subprocess
import requests
import signal as signal_module

from dotenv import load_dotenv

load_dotenv(os.path.expanduser('~/sentinel/.env'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler(
            os.path.expanduser('~/sentinel/logs/telegram.log')
        ),
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')
bot_process = None

# Bot state
_paused = False


def is_paused() -> bool:
    return _paused


def is_market_open_check() -> bool:
    try:
        import pytz
        from datetime import datetime
        est = pytz.timezone('US/Eastern')
        now = datetime.now(est)
        if now.weekday() >= 5:
            return False
        return (
            now.hour > 9 or
            (now.hour == 9 and now.minute >= 30)
        ) and now.hour < 16
    except Exception:
        return False


def send(message: str):
    if not TOKEN or not CHAT_ID:
        logger.warning("Telegram credentials not set")
        return
    try:
        requests.post(
            f'https://api.telegram.org/bot{TOKEN}/sendMessage',
            json={'chat_id': CHAT_ID, 'text': message, 'parse_mode': 'HTML'},
            timeout=10,
        )
    except Exception as e:
        logger.error(f"send error: {e}")


def is_bot_running() -> bool:
    try:
        result = subprocess.run(
            ['pgrep', '-f', 'main.py'],
            capture_output=True,
        )
        return result.returncode == 0
    except Exception:
        return False


def start_bot():
    global bot_process
    if is_bot_running():
        send("⚠️ Bot is already running.")
        return
    sentinel_dir = os.path.expanduser('~/sentinel')
    log_path = os.path.join(sentinel_dir, 'logs', 'bot.log')
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, 'a') as log_file:
        bot_process = subprocess.Popen(
            [sys.executable, 'main.py'],
            cwd=sentinel_dir,
            stdout=log_file,
            stderr=log_file,
        )
    time.sleep(2)
    if is_bot_running():
        send("✅ Bot started successfully.")
        logger.info("main.py started")
    else:
        send("❌ Bot failed to start. Check logs.")


def stop_bot():
    if not is_bot_running():
        send("⚠️ Bot is not running.")
        return
    try:
        subprocess.run(['pkill', '-f', 'main.py'], check=False)
        time.sleep(2)
        send("🛑 Bot stopped.")
        logger.info("main.py stopped")
    except Exception as e:
        send(f"❌ Stop failed: {e}")


def restart_bot():
    send("🔄 Restarting bot...")
    stop_bot()
    time.sleep(2)
    start_bot()


def handle_control_command(text: str) -> bool:
    global _paused
    cmd = text.strip().lower()

    if cmd in ('start', 'run'):
        start_bot()
        return True

    if cmd in ('stop', 'halt'):
        stop_bot()
        return True

    if cmd == 'restart':
        restart_bot()
        return True

    if cmd in ('pause', '/pause'):
        _paused = True
        send(
            "⏸ SENTINEL PAUSED\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Bot will NOT scan for new trades\n"
            "Still monitoring open positions\n"
            "Still sending exit alerts\n\n"
            "You are in manual control\n\n"
            "To resume: text RESUME\n"
            "To check status: text STATUS"
        )
        try:
            requests.post(
                'http://localhost:5001/pause',
                timeout=3,
            )
        except Exception:
            pass
        return True

    if cmd in ('resume', '/resume'):
        _paused = False
        send(
            "▶️ SENTINEL RESUMED\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Bot scanning every 45 minutes\n"
            "Morning brief at 9am EST\n"
            "Exit alerts active\n\n"
            "Back in auto mode!"
        )
        try:
            requests.post(
                'http://localhost:5001/resume',
                timeout=3,
            )
        except Exception:
            pass
        return True

    if cmd in ('status', '/status'):
        running = is_bot_running()
        paused = is_paused()

        if not running:
            bot_status = "🔴 STOPPED"
            action = "Text START to begin"
        elif paused:
            bot_status = "⏸ PAUSED (manual mode)"
            action = "Text RESUME to go auto"
        else:
            bot_status = "🟢 RUNNING (auto mode)"
            action = "Text PAUSE for manual control"

        send(
            f"⚡ SENTINEL STATUS\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Bot: {bot_status}\n"
            f"Market: "
            f"{'🟢 OPEN' if is_market_open_check() else '🔴 CLOSED'}\n\n"
            f"{action}"
        )
        return True

    if cmd in ('help', '/help', '/start', 'menu'):
        send(
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
            "analyze NVDA — Analyze any stock\n"
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
        return True

    return False


def get_updates(offset=None):
    if not TOKEN:
        return []
    try:
        params = {'timeout': 30, 'allowed_updates': ['message']}
        if offset is not None:
            params['offset'] = offset
        resp = requests.get(
            f'https://api.telegram.org/bot{TOKEN}/getUpdates',
            params=params,
            timeout=40,
        )
        data = resp.json()
        if data.get('ok'):
            return data.get('result', [])
    except Exception as e:
        logger.error(f"get_updates error: {e}")
    return []


def _graceful_shutdown(signum, frame):
    logger.info("Sentinel Telegram listener shutting down")
    send("📴 Telegram listener shutting down.")
    sys.exit(0)


def run():
    signal_module.signal(signal_module.SIGTERM, _graceful_shutdown)
    signal_module.signal(signal_module.SIGINT, _graceful_shutdown)

    logger.info("Sentinel Telegram listener started")
    send(
        "<b>📡 SENTINEL LISTENER ONLINE</b>\n\n"
        "<b>🤖 Bot Controls:</b>\n"
        "start / stop / restart\n"
        "pause — Manual mode\n"
        "resume — Auto mode\n"
        "status — Health check\n\n"
        "<b>📡 Scanning:</b>\n"
        "scan / top3 / discover / watchlist\n\n"
        "<b>📊 Analysis:</b>\n"
        "analyze NVDA / holdings / portfolio\n"
        "budget / stats / goal\n\n"
        "<b>📱 Manual Trades:</b>\n"
        "bought NVDA 0.5 245.50\n"
        "sold NVDA 0.25 261.00\n\n"
        "Text <b>help</b> for full command list"
    )

    offset = None
    while True:
        try:
            updates = get_updates(offset)
            for update in updates:
                offset = update['update_id'] + 1
                msg = update.get('message', {})
                text = msg.get('text', '').strip()
                if not text:
                    continue

                logger.info(f"Received: {text}")

                if handle_control_command(text):
                    continue

                try:
                    sys.path.insert(
                        0, os.path.expanduser('~/sentinel')
                    )
                    from backend.telegram.handler import handle_command
                    handle_command(text)
                except Exception as e:
                    logger.error(f"handle_command error: {e}")
                    send(f"❌ Error: {e}")
        except Exception as e:
            logger.error(f"run loop error: {e}")
            time.sleep(5)


if __name__ == '__main__':
    run()
