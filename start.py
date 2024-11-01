import os
import requests
from datetime import datetime, timedelta
import hmac
import hashlib
import json
import time
import base64

# the interval to change my offer book
interval = 2
# how much percentage rate based on whole market
rate_cut_ratio = 0.85
# increment rate by 0.01% in my offer
rate_increment = 0.01

"""Get funding book data from Bitfinex"""
def get_market_funding_book(currency='fUSD'):
    #total volume in whole market
    market_fday_volume_dict = {2: 0, 30: 0, 60: 0, 120: 0}
    #highest rate in each day set whole market
    market_frate_upper_dict = {2: -999, 30: -999, 60: -999, 120: -999}
    # lowest rate in each day set whole market
    market_frate_lower_dict = {2: 999000, 30: 999000, 60: 999000, 120: 999000}

    """Get funding book data from Bitfinex"""
    for page in range(5):
        url = f"https://api-pub.bitfinex.com/v2/book/fUST/P{page}?len=250"
        response = requests.get(url)
        response.raise_for_status()
        book_data = response.json()
        for offer in book_data:
            numdays = offer[2]
            if(numdays == 2):
                market_fday_volume_dict[2] += abs(offer[1]) 
                market_frate_upper_dict[2] = max(market_frate_upper_dict[2], offer[0])
                market_frate_lower_dict[2] = min(market_frate_lower_dict[2], offer[0])
            elif(numdays > 29) and (numdays < 61):
                market_fday_volume_dict[30] += abs(offer[1])
                market_frate_upper_dict[30] = max(market_frate_upper_dict[30], offer[0])
                market_frate_lower_dict[30] = min(market_frate_lower_dict[30], offer[0])
            elif(numdays > 60) and (numdays < 120):
                market_fday_volume_dict[60] += abs(offer[1])
                market_frate_upper_dict[60] = max(market_frate_upper_dict[60], offer[0])
                market_frate_lower_dict[60] = min(market_frate_lower_dict[60], offer[0])
            elif(numdays > 120):
                market_fday_volume_dict[120] += abs(offer[1])
                market_frate_upper_dict[120] = max(market_frate_upper_dict[120], offer[0])
                market_frate_lower_dict[120] = min(market_frate_lower_dict[120], offer[0])

    # return total volume, highest rate, lowest rate
    return market_fday_volume_dict,market_frate_upper_dict,market_frate_lower_dict


"""Guess offer rate from funding book data"""
def guess_funding_book(volume_dict,rate_upper_dict,rate_lower_dict):
    total_volume = sum(volume_dict.values())
    margin_split_ratio_dict = { 2: volume_dict[2]/total_volume, 30: volume_dict[30]/total_volume, 60: volume_dict[60]/total_volume, 120: volume_dict[120]/total_volume}
    rate_guess = { 2: rate_cut_ratio*rate_upper_dict[2], 30: rate_cut_ratio*rate_upper_dict[30], 60: rate_cut_ratio*rate_upper_dict[60], 120: rate_cut_ratio*rate_upper_dict[120]}
    return margin_split_ratio_dict,rate_guess


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
    volume_dict,rate_upper_dict,rate_lower_dict = get_market_funding_book(currency)
    
    # guess market rate
    margin_split_ratio_dict,offer_rate_guess = guess_funding_book(volume_dict,rate_upper_dict,rate_lower_dict)

    # remove current offer first
    remove_lending_offer(currency)

    # place new offer
    place_lending_offer(currency, margin_split_ratio_dict,offer_rate_guess)
    

if __name__ == "__main__":
    lending_bot_strategy()
