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
    if cmd == 'status':
        running = is_bot_running()
        status = "🟢 Running" if running else "🔴 Stopped"
        send(
            f"<b>SENTINEL STATUS</b>\n"
            f"Main bot: {status}\n"
            f"Telegram listener: 🟢 Running\n"
            f"Dashboard: http://localhost:8501"
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
        "<b>Bot Controls:</b>\n"
        "start — Start the trading bot\n"
        "stop — Stop the trading bot\n"
        "restart — Restart the trading bot\n"
        "status — Check bot status\n\n"
        "<b>Trading Commands:</b>\n"
        "scan — Scan watchlist\n"
        "top3 — Best 3 signals\n"
        "analyze NVDA — Analyze a stock\n"
        "holdings — Open positions\n"
        "portfolio — Budget + positions\n"
        "watchlist — Show watchlist\n"
        "budget — Show budget\n"
        "discover — Find new stocks\n"
        "goal — Car fund progress\n"
        "stats — Performance\n"
        "pause / resume — Pause scanning\n"
        "help — Full command list"
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
