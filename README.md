# SENTINEL — ETF Swing Trading System

## Module Status
- [x] Module 1: Market Data Engine
- [x] Module 2: Strategy Engine
- [x] Module 3: Risk Engine
- [x] Module 4: Portfolio Tracker
- [x] Module 5: Execution Engine
- [x] Module 6: Journal/Logging
- [x] Dashboard: Streamlit

## Setup
```
pip install -r requirements.txt
cp .env.example .env       # fill in your keys
```

## How to run
```
python3.11 main.py                  # run full bot (45-min scan loop)
python3.11 main.py scan             # run one scan and exit
python3.11 main.py status           # show positions + stats
streamlit run streamlit_app.py      # launch dashboard
```

## Run tests
```
python3.11 -m pytest tests/
```
