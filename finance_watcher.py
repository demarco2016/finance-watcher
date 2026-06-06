import requests
import os
import time
from dotenv import load_dotenv

load_dotenv()

def get_top10():
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": 10,
        "page": 1
    }
    res = requests.get(url, params=params)
    return res.json()

def check_alerts(alerts):
    print("\n📈 Finance Watcher - Top 10 by Market Cap\n")
    coins = get_top10()
    for coin in coins:
        name = coin["symbol"].upper()
        price = coin["current_price"]
        change = coin["price_change_percentage_24h"]
        arrow = "🟢" if change > 0 else "🔴"
        print(f"  {arrow} {name}: ${price:,} ({change:+.2f}%)")
        
        if coin["id"] in alerts:
            if price <= alerts[coin["id"]]["low"]:
                print(f"     ⚠️  ALERT: hit low target ${alerts[coin['id']]['low']}")
            elif price >= alerts[coin["id"]]["high"]:
                print(f"     ⚠️  ALERT: hit high target ${alerts[coin['id']]['high']}")
    print()

# ===== EDIT THIS =====
alerts = {
    "bitcoin": {"low": 90000, "high": 110000},
    "ethereum": {"low": 2000, "high": 4000},
}
REFRESH_MINUTES = 5
# =====================

while True:
    check_alerts(alerts)
    print(f"  ⏳ Next check in {REFRESH_MINUTES} min...\n")
    time.sleep(REFRESH_MINUTES * 60)
