# 📈 Finance Watcher

Real-time crypto price tracker with custom alerts — runs on WSL2/Ubuntu.

## Features
- 🔟 Top 10 coins by market cap (live)
- 🔴🟢 24h price change indicators
- ⚠️ Custom high/low price alerts
- ⏰ Auto-refresh every 5 minutes

## Setup

```bash
pip3 install requests python-dotenv
cp .env.example .env
# Add your OpenRouter API key in .env
```

## Usage

```bash
python3 finance_watcher.py
```

## Stack
- Python 3.12
- CoinGecko API (free, no key needed)
- WSL2 / Ubuntu
