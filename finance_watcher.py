import requests, os, time
from dotenv import load_dotenv
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})

def get_top10():
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {"vs_currency": "usd", "order": "market_cap_desc", "per_page": 10, "page": 1}
    return requests.get(url, params=params).json()

def check_alerts(alerts):
    print("\nFinance Watcher - Top 10\n")
    summary = "Finance Watcher\n\n"
    for coin in get_top10():
        name = coin["symbol"].upper()
        price = coin["current_price"]
        change = coin["price_change_percentage_24h"]
        arrow = "UP" if change > 0 else "DOWN"
        line = f"{arrow} {name}: ${price:,} ({change:+.2f}%)"
        print(line)
        summary += line + "\n"
        if coin["id"] in alerts:
            if price <= alerts[coin["id"]]["low"]:
                msg = f"ALERT: {name} hit LOW ${alerts[coin['id']]['low']}"
                print(msg)
                send_telegram(msg)
            elif price >= alerts[coin["id"]]["high"]:
                msg = f"ALERT: {name} hit HIGH ${alerts[coin['id']]['high']}"
                print(msg)
                send_telegram(msg)
    send_telegram(summary)

alerts = {"bitcoin": {"low": 90000, "high": 110000}, "ethereum": {"low": 2000, "high": 4000}}
REFRESH_MINUTES = 5

while True:
    check_alerts(alerts)
    print(f"\nNext check in {REFRESH_MINUTES} min...\n")
    time.sleep(REFRESH_MINUTES * 60)
