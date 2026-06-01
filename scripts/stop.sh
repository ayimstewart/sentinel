#!/bin/bash
pkill -f "main.py"
pkill -f "sentinel_telegram.py"
pkill -f "streamlit"
echo "✅ Sentinel stopped"
