#!/bin/bash
cd ~/sentinel

# Start Ollama if not running
if ! pgrep -x "ollama" > /dev/null; then
    ollama serve &
    sleep 3
fi

# Start Telegram listener (always on)
nohup python3.11 sentinel_telegram.py > ~/sentinel/logs/telegram.log 2>&1 &

# Start main bot
nohup python3.11 main.py > ~/sentinel/logs/bot.log 2>&1 &

# Start dashboard
nohup streamlit run streamlit_app.py --server.port 8501 --server.address 0.0.0.0 > ~/sentinel/logs/dashboard.log 2>&1 &

sleep 2
echo "✅ Sentinel started"
open http://localhost:8501
