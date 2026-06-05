#!/bin/bash
cd ~/sentinel

echo "⚡ Starting Sentinel..."

# Create logs folder
mkdir -p ~/sentinel/logs

# Start Ollama if not running
if ! pgrep -x "ollama" > /dev/null; then
    echo "Starting Ollama..."
    ollama serve &
    sleep 3
fi

# Start Telegram listener
nohup python3.11 ~/sentinel/sentinel_telegram.py > ~/sentinel/logs/telegram.log 2>&1 &
echo "✅ Telegram listener started"
sleep 1

# Start main bot
nohup python3.11 ~/sentinel/main.py > ~/sentinel/logs/bot.log 2>&1 &
echo "✅ Main bot started"
sleep 1

# Start dashboard
nohup streamlit run ~/sentinel/streamlit_app.py --server.port 8501 --server.address 0.0.0.0 > ~/sentinel/logs/dashboard.log 2>&1 &
echo "✅ Dashboard started"

sleep 2
open http://localhost:8501
echo "━━━━━━━━━━━━━━━━━━━━"
echo "Sentinel fully started!"
echo "Dashboard: http://localhost:8501"
echo "Text your Telegram bot: status"
