import os
import requests
from datetime import datetime, timedelta
import hmac
import hashlib
import json
import time
import base64

def get_market_funding_book(currency='fUSD'):
    """Get funding book data from Bitfinex"""
    book_data = []
    for page in range(5):
        url = f"https://api-pub.bitfinex.com/v2/book/fUST/P{page}?len=250"
        response = requests.get(url)
        response.raise_for_status()
        book_data.extend(response.json())

    print(book_data)

def analyze_funding_book(book_data):
    """Analyze funding book data"""
    # TODO: implement
    return 0

def get_history_rate():
    """Get history rate data from Bitfinex"""
    # TODO: implement
    return 0

# remove current offer in my book
def remove_lending_offer(currency, offer_id):
    """Remove a lending offer on Bitfinex"""
    # TODO: implement
    return 0

# https://docs.bitfinex.com/#submit-a-funding-offer
def place_lending_offer(currency, offer_rate):
    """Place a lending offer on Bitfinex
    
    Args:
        currency (str): The currency to lend (e.g., 'UST', 'USD')
        amount (float): Amount to lend
        rate (float): Daily interest rate (in percentage)
    
    Returns:
        dict: Response from the API
    """
    API_KEY = os.getenv('BITFINEX_API_KEY')
    API_SECRET = os.getenv('BITFINEX_API_SECRET')
    
    if not API_KEY or not API_SECRET:
        raise ValueError("API credentials not found in environment variables")
    
    nonce = str(int(time.time() * 1000))
    path = "v2/auth/w/funding/offer/submit"
    url = f"https://api.bitfinex.com/{path}"
    
    # Prepare the payload
    body = {
        'type': 'LIMIT',
        'symbol': f'f{currency}',
        'amount': str(amount),
        'rate': str(rate / 365),  # Convert daily rate to yearly
        'period': 2,  # Default period in days
        'flags': 0
    }
    
    # Create signature
    body_json = json.dumps(body)
    signature = f"/api/{path}{nonce}{body_json}"
    h = hmac.new(API_SECRET.encode('utf8'), signature.encode('utf8'), hashlib.sha384)
    signature = h.hexdigest()
    
    # Prepare headers
    headers = {
        "bfx-nonce": nonce,
        "bfx-apikey": API_KEY,
        "bfx-signature": signature,
        "content-type": "application/json"
    }
    

    '''
        OFFER_STRATEGY :
        1. Default 2 days
        2. If rate is high, set to 30 days
        3. If rate is low, set to 5 days
        4. If amount is high, set to 30 days
        5. If amount is low, set to 5 days
    '''
    days = 2
    if offer_rate * 36500 > 30:
        days = 30
    elif offer_rate * 36500 > 25:
        days = 20
    elif offer_rate * 36500 > 20:
        days = 10
    elif offer_rate * 36500 > 15:
        days = 5

    # calculate amount
    amount = get_funding_for_offer(currency)

    if amount / MIN_FUNDING_AMOUNT[currency] > 2 and offer_rate * 36500 < 15:
        amount = MIN_FUNDING_AMOUNT[currency]

    amount_str = ("%.6f" % abs(amount))[
        :-1
    ]  # Truncate at 5th decimal places to avoid rounding error


    # Send request
    response = requests.post(url, headers=headers, data=body_json)
    response.raise_for_status()
    
    return response.json()

def lending_bot_strategy():
    currency = os.getenv('FUND_CURRENCY')
    # get market rate
    market_rate_usdt = get_market_funding_book(currency)
    
    # analyze market rate
    highest_offer_rate = analyze_funding_book(market_rate_usdt)

    # remove current offer first
    remove_lending_offer(currency)

    # place new offer
    place_lending_offer(currency, highest_offer_rate)
    

if __name__ == "__main__":
    lending_bot_strategy()
