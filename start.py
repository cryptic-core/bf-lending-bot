import os
from dotenv import load_dotenv
load_dotenv()
import requests
from datetime import datetime, timedelta
import hmac
import hashlib
import json

# API ENDPOINTS
API = "https://api.bitfinex.com/v2"
BITFINEX_PUBLIC_API_URL = "https://api-pub.bitfinex.com"

""" Strategy Parameters, Modify here"""
STEPS = 10 # number of steps to offer at each day interval
rate_increment = 0.001 # increment of rate on each step
interval = 2 # how frequently(in hours) to replace my offer  
rate_adjustment_ratio = 0.5 # how much to adjust my offer rate based on market offerbook


API_KEY, API_SECRET = (
    os.getenv("BF_API_KEY"),
    os.getenv("BF_API_SECRET")
)
# Copy from https://docs.bitfinex.com/docs/rest-auth
def _build_authentication_headers(endpoint, payload = None):
    nonce = str(round(datetime.now().timestamp() * 1_000))

    message = f"/api/v2/{endpoint}{nonce}"

    if payload != None:
        message += json.dumps(payload)

    signature = hmac.new(
        key=API_SECRET.encode("utf8"),
        msg=message.encode("utf8"),
        digestmod=hashlib.sha384
    ).hexdigest()

    return {
        "bfx-apikey": API_KEY,
        "bfx-nonce": nonce,
        "bfx-signature": signature
    }
  

"""Get funding book data from Bitfinex"""
def get_market_funding_book(currency='fUSD'):
    #total volume in whole market
    market_fday_volume_dict = {2: 0, 30: 0, 60: 0, 120: 0}
    #highest rate in each day set whole market
    market_frate_upper_dict = {2: -999, 30: -999, 60: -999, 120: -999}
    # weighted average rate in each day set whole market
    market_frate_ravg_dict = {2: 0, 30: 0, 60: 0, 120: 0}

    """Get funding book data from Bitfinex"""
    for page in range(5):
        url = f"{BITFINEX_PUBLIC_API_URL}/v2/book/fUST/P{page}?len=250"
        response = requests.get(url)
        response.raise_for_status()
        book_data = response.json()
        for offer in book_data:
            numdays = offer[2]
            if(numdays == 2):
                market_fday_volume_dict[2] += abs(offer[3]) 
                market_frate_upper_dict[2] = max(market_frate_upper_dict[2], offer[0])
                market_frate_ravg_dict[2] += offer[0] * abs(offer[3]) 
            elif(numdays > 29) and (numdays < 61):
                market_fday_volume_dict[30] += abs(offer[3])
                market_frate_upper_dict[30] = max(market_frate_upper_dict[30], offer[0])
                market_frate_ravg_dict[30] += offer[0] * abs(offer[3]) 
            elif(numdays > 60) and (numdays < 120):
                market_fday_volume_dict[60] += abs(offer[3])
                market_frate_upper_dict[60] = max(market_frate_upper_dict[60], offer[0])
                market_frate_ravg_dict[60] += offer[0] * abs(offer[3])
            elif(numdays > 120):
                market_fday_volume_dict[120] += abs(offer[3])
                market_frate_upper_dict[120] = max(market_frate_upper_dict[120], offer[0])
                market_frate_ravg_dict[120] += offer[0] * abs(offer[3])

    market_frate_ravg_dict[2] /= market_fday_volume_dict[2]
    market_frate_ravg_dict[30] /= market_fday_volume_dict[30]
    market_frate_ravg_dict[60] /= market_fday_volume_dict[60]
    market_frate_ravg_dict[120] /= market_fday_volume_dict[120]

    print("market_fday_volume_dict:")
    print(market_fday_volume_dict)
    print("market_frate_upper_dict:")
    print(market_frate_upper_dict)
    print("market_frate_ravg_dict:")
    print(market_frate_ravg_dict)
    # return total volume, highest rate, lowest rate
    return market_fday_volume_dict,market_frate_upper_dict,market_frate_ravg_dict

"""Calculate how FOMO the market is"""
def get_market_borrow_sentiment(currency='fUSD'):
    
    url = f"{BITFINEX_PUBLIC_API_URL}/v2/funding/stats/{currency}/hist"
    response = requests.get(url)
    response.raise_for_status()
    fdata = response.json()
    funding_amount_used_today = fdata[0][8]
    funding_amount_used_avg = 0
    # get last 7 days average volume
    for n in range(1,8):
        rate = fdata[n][3]
        funding_amount_used_avg += fdata[n][8]
        
    funding_amount_used_avg /= 7
    sentiment = funding_amount_used_today/funding_amount_used_avg
    print(f"funding_amount_used_today: {funding_amount_used_today}, funding_amount_used_avg: {funding_amount_used_avg}, sentiment: {sentiment}")
    return sentiment
        

"""Guess offer rate from funding book data"""
def guess_funding_book(volume_dict,rate_upper_dict,sentiment):
    mutiplier = rate_adjustment_ratio * sentiment
    total_volume = sum(volume_dict.values())
    margin_split_ratio_dict = { 2: volume_dict[2]/total_volume, 30: volume_dict[30]/total_volume, 60: volume_dict[60]/total_volume, 120: volume_dict[120]/total_volume}
    # rate guess, we use market highest here only
    rate_guess = { 2: mutiplier*rate_upper_dict[2], 30: mutiplier*rate_upper_dict[30], 60: sentiment*rate_upper_dict[60], 120: mutiplier*rate_upper_dict[120]}
    print(f"margin_split_ratio_dict: {margin_split_ratio_dict}, rate_guess: {rate_guess}")
    return margin_split_ratio_dict,rate_guess


""" get all offers in my book """
def list_lending_offers():
    endpoint = "auth/r/funding/offers/Symbol"
    payload = {}
    headers = {
        "Content-Type": "application/json",
        **_build_authentication_headers(endpoint, payload)
    }
    url = f"{API}/{endpoint}"
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()

""" remove current offer in my book """
def remove_all_lending_offer():
    endpoint = "auth/w/funding/offer/cancel/all"
    payload = {}
    headers = {
        "Content-Type": "application/json",
        **_build_authentication_headers(endpoint, payload)
    }
    url = f"{API}/{endpoint}"
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()

"""Get available funds"""
def available_funds():
    endpoint = "auth/r/info/margin/key"
    payload = {}
    headers = {
        "Content-Type": "application/json",
        **_build_authentication_headers(endpoint, payload)
    }
    url = f"{API}/{endpoint}"
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()



""" Main Function: Strategically place a lending offer on Bitfinex"""
def place_lending_offer(currency, margin_split_ratio_dict,offer_rate_guess):
    """
    Args:
        currency (str): The currency to lend (e.g., 'UST', 'USD')
        amount (float): Amount to lend
        rate (float): Daily interest rate (in percentage)
    
    Returns:
        dict: Response from the API
    """
    available_funds = available_funds()
    endpoint = "auth/w/funding/offer/submit"

    for period in margin_split_ratio_dict.keys():
        splited_fund = round(margin_split_ratio_dict[period] * available_funds, 2)
        rate = round(offer_rate_guess[period], 5)
        for i in range(STEPS):
            # FRRDELTAFIX: Place an order at an implicit, static rate, relative to the FRR
            # FRRDELTAVAR: Place an order at an implicit, dynamic rate, relative to the FRR
            payload = {
                "type": "FRRDELTAVAR",
                "symbol": currency,
                "amount": splited_fund,
                "rate": rate + i * rate_increment,
                "period": period,
                "flags": 0
            }
            headers = {
                "Content-Type": "application/json",
            **_build_authentication_headers(endpoint, payload)
        }
        url = f"{API}/{endpoint}"
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()


def lending_bot_strategy():
    
    print("Running lending bot strategy")
    currency = os.getenv('FUND_CURRENCY')
    # get market sentiment
    sentiment = get_market_borrow_sentiment(currency)
    # get market rate
    volume_dict,rate_upper_dict,rate_lower_dict = get_market_funding_book(currency)
    
    # guess market rate
    margin_split_ratio_dict,offer_rate_guess = guess_funding_book(volume_dict,rate_upper_dict,sentiment)

    # get my offers and remove current offer first
    my_offers = list_lending_offers()
    print(f"my_offers: {my_offers}")
    remove_all_lending_offer()

    # place new offer
    place_lending_offer(currency, margin_split_ratio_dict,offer_rate_guess)
    

if __name__ == "__main__":
    lending_bot_strategy()
