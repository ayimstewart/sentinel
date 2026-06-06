# Market filters — never trade these
MARKET_FILTERS = ['SPY', 'QQQ', 'IWM']

# ETF long term holds — never swing trade
ETF_LONG_TERM = [
    'VOO', 'QQQ', 'SPY', 'GLD', 'IWM'
]

# SWING UNIVERSE — high quality growth stocks
# Backtest proven, liquid, trending sectors
SWING_UNIVERSE = {
    'ai_tech': [
        'NVDA', 'MSFT', 'META', 'GOOGL'
    ],
    'semiconductors': [
        'ASML', 'AMD', 'AVGO', 'TSM'
    ],
    'cybersecurity': [
        'CRWD', 'PANW', 'ZS', 'FTNT'
    ],
    'software': [
        'NOW', 'PLTR', 'SNOW', 'MDB'
    ],
    'fintech': [
        'HOOD', 'SOFI', 'SQ', 'AFRM'
    ],
    'space_defense': [
        'RKLB', 'ASTS', 'LMT', 'RTX'
    ],
    'nuclear_energy': [
        'OKLO', 'SMR', 'CEG', 'VST'
    ],
    'social_media': [
        'RDDT', 'SNAP', 'PINS'
    ],
    'biotech': [
        'MRNA', 'NVAX', 'BNTX'
    ],
    'consumer_tech': [
        'AAPL', 'AMZN', 'TSLA'
    ],
}

# All swing tickers flattened
SWING_TICKERS = [
    ticker
    for tickers in SWING_UNIVERSE.values()
    for ticker in tickers
]

# Highest quality stocks — scan universe
CORE_WATCHLIST = [
    'NVDA',  # AI leader
    'AAPL',  # Core tech
    'MSFT',  # AI + cloud
    'META',  # Social + AI
    'CRWD',  # Cyber leader
    'ASML',  # Semi equipment
    'NOW',   # Enterprise software
    'PLTR',  # AI + data
    'RKLB',  # Space
    'HOOD',  # Fintech
    'RDDT',  # Social
    'OKLO',  # Nuclear
]

# Your personal stocks — always scan first
MY_STOCKS = [
    'NVDA', 'AAPL', 'GRAB',
    'AGIX', 'XEL', 'NBIS',
]

# Backward compat alias
MY_ROBINHOOD_STOCKS = MY_STOCKS

# Max stocks per scan for speed
MAX_SCAN_STOCKS = 15

# Sector mapping for risk engine
SECTORS = {
    'NVDA': 'ai_tech',
    'MSFT': 'ai_tech',
    'META': 'ai_tech',
    'GOOGL': 'ai_tech',
    'AAPL': 'consumer_tech',
    'AMZN': 'consumer_tech',
    'TSLA': 'consumer_tech',
    'ASML': 'semiconductors',
    'AMD': 'semiconductors',
    'AVGO': 'semiconductors',
    'TSM': 'semiconductors',
    'CRWD': 'cybersecurity',
    'PANW': 'cybersecurity',
    'ZS': 'cybersecurity',
    'FTNT': 'cybersecurity',
    'NOW': 'software',
    'PLTR': 'software',
    'SNOW': 'software',
    'MDB': 'software',
    'HOOD': 'fintech',
    'SOFI': 'fintech',
    'SQ': 'fintech',
    'AFRM': 'fintech',
    'RKLB': 'space_defense',
    'ASTS': 'space_defense',
    'LMT': 'space_defense',
    'RTX': 'space_defense',
    'OKLO': 'nuclear_energy',
    'SMR': 'nuclear_energy',
    'CEG': 'nuclear_energy',
    'VST': 'nuclear_energy',
    'RDDT': 'social_media',
    'SNAP': 'social_media',
    'PINS': 'social_media',
    'MRNA': 'biotech',
    'NVAX': 'biotech',
    'BNTX': 'biotech',
    'GRAB': 'fintech',
    'AGIX': 'ai_tech',
    'XEL': 'utilities',
    'NBIS': 'speculative',
    'PENG': 'speculative',
    'ADAPY': 'speculative',
}


def get_sector(ticker):
    return SECTORS.get(ticker, 'other')


# Priority scan order: personal stocks first, then core watchlist
SCAN_PRIORITY = list(dict.fromkeys(
    MY_STOCKS + CORE_WATCHLIST
))
