import os
import logging
from dotenv import load_dotenv
load_dotenv(os.path.expanduser('~/sentinel/.env'))

logger = logging.getLogger(__name__)

def explain_setup(ticker, strategy, score, features):
    try:
        import ollama
        prompt = f"""
Explain this ETF setup in 2 sentences.
Be factual. No buy/sell advice.

ETF: {ticker}
Strategy: {strategy}
Score: {score}/100
RSI: {features.get('rsi', 0):.0f}
Volume: {features.get('volume_ratio', 0):.1f}x avg
ATR: {features.get('atr_pct', 0):.1f}%"""

        model = os.getenv('OPERATIONAL_MODEL', 'qwen2.5:7b')
        resp = ollama.chat(
            model=model,
            messages=[{'role': 'user', 'content': prompt}],
            keep_alive=0,
            options={'num_ctx': 256}
        )
        return resp['message']['content']
    except Exception as e:
        logger.warning(f"AI error: {e}")
        return f"{strategy} setup on {ticker}. Score: {score}/100."

def summarize_news(ticker, headlines):
    if not headlines:
        return 'No recent news.'
    try:
        import ollama
        text = '\n'.join(headlines[:3])
        prompt = f"Summarize {ticker} news in one sentence. Bullish/bearish/neutral?\n{text}"
        model = os.getenv('OPERATIONAL_MODEL', 'qwen2.5:7b')
        resp = ollama.chat(
            model=model,
            messages=[{'role': 'user', 'content': prompt}],
            keep_alive=0,
            options={'num_ctx': 128}
        )
        return resp['message']['content']
    except Exception as e:
        return 'News unavailable.'
