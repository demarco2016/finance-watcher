"""Read-only CoinGecko price monitor with optional Telegram notifications."""
import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

MARKETS_URL = 'https://api.coingecko.com/api/v3/coins/markets'
REQUEST_TIMEOUT = (5, 20)


class WatcherError(Exception):
    """An actionable error safe to display without credentials."""


def is_number(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def load_alerts(path):
    if path is None:
        return {}
    try:
        alerts = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise WatcherError('Cannot read alerts file: provide valid JSON.') from error
    if not isinstance(alerts, dict):
        raise WatcherError('Alerts must be a JSON object keyed by coin ID.')
    for coin_id, limits in alerts.items():
        if not coin_id.strip() or not isinstance(limits, dict) or not limits:
            raise WatcherError('Each coin must have at least one low/high threshold.')
        if set(limits) - {'low', 'high'}:
            raise WatcherError('Only low and high thresholds are supported.')
        if any(not is_number(value) or value < 0 for value in limits.values()):
            raise WatcherError('Thresholds must be finite, non-negative numbers.')
        if 'low' in limits and 'high' in limits and limits['low'] >= limits['high']:
            raise WatcherError('A low threshold must be below the high threshold.')
    return alerts


def get_top10(session):
    try:
        response = session.get(
            MARKETS_URL,
            params={'vs_currency': 'usd', 'order': 'market_cap_desc', 'per_page': 10, 'page': 1},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        coins = response.json()
    except (requests.RequestException, ValueError) as error:
        raise WatcherError('CoinGecko request failed; no fresh prices are available.') from error
    if not isinstance(coins, list) or not coins:
        raise WatcherError('CoinGecko returned an empty or invalid market response.')
    for coin in coins:
        if not isinstance(coin, dict):
            raise WatcherError('CoinGecko returned an invalid coin record.')
        if any(not isinstance(coin.get(key), str) or not coin[key].strip() for key in ('id', 'symbol')):
            raise WatcherError('CoinGecko returned a coin without an ID or symbol.')
        price, change = coin.get('current_price'), coin.get('price_change_percentage_24h')
        if not is_number(price) or price < 0:
            raise WatcherError('CoinGecko returned an unavailable or invalid price.')
        if change is not None and not is_number(change):
            raise WatcherError('CoinGecko returned an invalid 24-hour change.')
    return coins


def build_report(coins, alerts):
    lines = ['Finance Watcher - Top 10 (USD)']
    for coin in coins:
        symbol, price = coin['symbol'].upper(), coin['current_price']
        change = coin.get('price_change_percentage_24h')
        if change is None:
            movement, change_text = 'N/A', '24h unavailable'
        else:
            movement = 'UP' if change > 0 else 'DOWN' if change < 0 else 'FLAT'
            change_text = f'{change:+.2f}%'
        lines.append(f'{movement} {symbol}: ${price:,.8g} ({change_text})')
        limits = alerts.get(coin['id'], {})
        if 'low' in limits and price <= limits['low']:
            lines.append(f"ALERT: {symbol} hit LOW ${limits['low']:,}")
        elif 'high' in limits and price >= limits['high']:
            lines.append(f"ALERT: {symbol} hit HIGH ${limits['high']:,}")
    missing = set(alerts) - {coin['id'] for coin in coins}
    if missing:
        lines.append('Not in current top 10; thresholds not checked: ' + ', '.join(sorted(missing)))
    return '\n'.join(lines)


def send_telegram(session, message, token, chat_id):
    if not token or not chat_id:
        raise WatcherError('Telegram requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.')
    try:
        response = session.post(
            f'https://api.telegram.org/bot{token}/sendMessage',
            data={'chat_id': chat_id, 'text': message}, timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        result = response.json()
    except (requests.RequestException, ValueError) as error:
        # Telegram request exception text may include the token in its URL.
        raise WatcherError('Telegram delivery failed; check credentials and connectivity.') from error
    if not isinstance(result, dict) or result.get('ok') is not True:
        raise WatcherError('Telegram rejected the notification.')


def refresh_minutes(value):
    try:
        minutes = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError('Refresh interval must be a number.') from error
    if not math.isfinite(minutes) or not 1 <= minutes <= 1440:
        raise argparse.ArgumentTypeError('Refresh interval must be between 1 and 1440 minutes.')
    return minutes


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once', action='store_true', help='Run one poll and exit.')
    parser.add_argument('--refresh-minutes', type=refresh_minutes, default=5, help='Interval in minutes (1–1440, default: 5).')
    parser.add_argument('--alerts', type=Path, help='JSON file of USD thresholds.')
    parser.add_argument('--telegram', action='store_true', help='Send each report to your configured Telegram chat.')
    args = parser.parse_args(argv)
    load_dotenv(Path(__file__).with_name('.env'))
    token = os.getenv('TELEGRAM_BOT_TOKEN', '').strip()
    chat_id = os.getenv('TELEGRAM_CHAT_ID', '').strip()
    try:
        alerts = load_alerts(args.alerts)
        if args.telegram and (not token or not chat_id):
            raise WatcherError('Telegram requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.')
    except WatcherError as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1
    try:
        with requests.Session() as session:
            while True:
                status = 0
                try:
                    report = build_report(get_top10(session), alerts)
                    print(report, flush=True)
                    if args.telegram:
                        send_telegram(session, report, token, chat_id)
                except WatcherError as error:
                    print(f'Error: {error}', file=sys.stderr, flush=True)
                    status = 1
                if args.once:
                    return status
                time.sleep(args.refresh_minutes * 60)
    except KeyboardInterrupt:
        return 0


if __name__ == '__main__':
    sys.exit(main())
