# Finance Watcher

A read-only Python command-line monitor for CoinGecko's current top ten coins
by market capitalization. It prints USD prices and 24-hour percentage changes,
checks optional price thresholds, and can send reports to a Telegram chat.
It does not connect to wallets, trade, or assess token safety.

## Installation

Requires Python 3.10 or newer. On Linux, macOS, or WSL:

```bash
git clone https://github.com/demarco2016/finance-watcher.git
cd finance-watcher
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python finance_watcher.py --once
```

On Windows PowerShell, create the environment with `py -m venv .venv` and
activate it with `.venv\Scripts\Activate.ps1`, then use the same Python commands.

## Usage

```bash
# Print one report, without sending messages
python finance_watcher.py --once

# Poll every five minutes (Ctrl+C stops the process)
python finance_watcher.py

# Choose a polling interval between 1 and 1440 minutes
python finance_watcher.py --refresh-minutes 10

# Use your own thresholds
cp alerts.example.json alerts.json
python finance_watcher.py --once --alerts alerts.json
```

Edit `alerts.json` to set meaningful thresholds for your own use; the example
values are illustrative, not market recommendations. Keys are CoinGecko coin
IDs, such as `bitcoin`, rather than ticker symbols. Each entry accepts a `low`
and/or `high` non-negative USD threshold. If both exist, `low` must be below
`high`. Prices equal to a threshold trigger an alert. No thresholds are active
unless you supply `--alerts`.

### Optional Telegram delivery

```bash
cp .env.example .env
# Edit .env locally, then explicitly enable delivery:
python finance_watcher.py --once --alerts alerts.json --telegram
```

Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env` beside the script, or
in your environment. Existing environment values take precedence. The bot must
have permission to send to that chat. Without `--telegram`, the program never
sends a Telegram message, even if credentials are present. Never commit `.env`
or paste credentials into issues; `.env` and local `alerts.json` are ignored.

Each successful polling cycle sends one report when Telegram is enabled.
Threshold alerts can repeat on every cycle while a price remains beyond the
threshold; there is no persistent alert history or deduplication.

## Data source and limitations

- Prices come from CoinGecko's public `/api/v3/coins/markets` endpoint in USD,
  ordered by market capitalization. No API key is configured by this tool.
  See [CoinGecko API documentation](https://docs.coingecko.com/reference/coins-markets).
- Only the current top ten returned coins are checked. A configured coin outside
  that set is reported as unchecked, not silently considered within its limits.
- This is aggregated market data, not an on-chain scan. No blockchain network,
  contract, liquidity pool, honeypot, or ownership checks are performed.
- Data may be delayed, and public API rate limits or access policies can change.
  This monitor is not a reliable real-time execution or risk-control system.
- Missing 24-hour changes display as unavailable; zero changes display as flat.
  Missing/invalid prices, HTTP failures, and malformed responses fail the poll
  explicitly. A failed fetch never produces a fresh-price report or an all-clear.
- Telegram delivery is checked for HTTP and API-level errors. Logs omit raw
  request exceptions because Telegram request URLs contain the bot token.
- Requests use a 5-second connection and 20-second read timeout. Continuous mode
  reports errors and retries after the configured polling interval. `--once`
  exits with status 1 on fetch, configuration, or delivery failure, and 0 on success.
- The tool provides no token safety guarantee and no airdrop eligibility claim.

## Development and verification

```bash
python -m unittest discover -s tests -v
python -m compileall -q finance_watcher.py tests
```

The tests mock HTTP calls and Telegram delivery; they do not require credentials
or send messages. GitHub Actions runs these checks on Python 3.10 and 3.12.
Use `--once` separately to check live API access in your own environment.
