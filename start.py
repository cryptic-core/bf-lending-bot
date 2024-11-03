import os,sys,time,platform
from dotenv import load_dotenv
load_dotenv()
import schedule
from concurrent.futures import ThreadPoolExecutor
import asyncio
import requests
import platform
from datetime import datetime, timedelta
import hmac
import hashlib
import json
import aiohttp

# API ENDPOINTS
API = "https://api.bitfinex.com/v2"
BITFINEX_PUBLIC_API_URL = "https://api-pub.bitfinex.com"

""" Strategy Parameters, Modify here"""
STEPS = 10 # number of steps to offer at each day interval
highest_sentiment = 5 # highest sentiment to adjust from fair rate to market highest rate
rate_adjustment_ratio = 1.01 # manually adjustment ratio
# interval = 1  


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
async def get_market_funding_book(currency='fUSD'):
    #total volume in whole market
    market_fday_volume_dict = {2: 1, 30: 1, 60: 1, 120: 1} # can't be 0
    #highest rate in each day set whole market
    market_frate_upper_dict = {2: -999, 30: -999, 60: -999, 120: -999}
    # weighted average rate in each day set whole market
    market_frate_ravg_dict = {2: 0, 30: 0, 60: 0, 120: 0}

    """Get funding book data from Bitfinex"""
    for page in range(5):
        url = f"{BITFINEX_PUBLIC_API_URL}/v2/book/fUST/P{page}?len=250"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                response.raise_for_status()
                book_data = await response.json()
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
async def get_market_borrow_sentiment(currency='fUSD'):
    
    url = f"{BITFINEX_PUBLIC_API_URL}/v2/funding/stats/{currency}/hist"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            response.raise_for_status()
            fdata = await response.json()
            funding_amount_used_today = fdata[0][8]
            funding_amount_used_avg = 0
            # get last 12 hour average volume
            for n in range(1,13):
                rate = fdata[n][3]
                funding_amount_used_avg += fdata[n][8]
                
            funding_amount_used_avg /= 12
            sentiment = funding_amount_used_today/funding_amount_used_avg
            print(f"funding_amount_used_today: {funding_amount_used_today}, funding_amount_used_avg: {funding_amount_used_avg}, sentiment: {sentiment}")
            return sentiment
        

"""Guess offer rate from funding book data"""
def guess_funding_book(volume_dict,rate_upper_dict,rate_avg_dict,sentiment):
    
    total_volume = sum(volume_dict.values())
    margin_split_ratio_dict = { 2: volume_dict[2]/total_volume, 30: volume_dict[30]/total_volume, 60: volume_dict[60]/total_volume, 120: volume_dict[120]/total_volume}
    # rate guess, we use market highest here only
    rate_guess_2 = rate_avg_dict[2] + (rate_upper_dict[2] - rate_avg_dict[2]) * (sentiment/highest_sentiment) * rate_adjustment_ratio
    rate_guess_30 = rate_avg_dict[30] + (rate_upper_dict[30] - rate_avg_dict[30]) * (sentiment/highest_sentiment) * rate_adjustment_ratio
    rate_guess_60 = rate_avg_dict[60] + (rate_upper_dict[60] - rate_avg_dict[60]) * (sentiment/highest_sentiment) * rate_adjustment_ratio
    rate_guess_120 = rate_avg_dict[120] + (rate_upper_dict[120] - rate_avg_dict[120]) * (sentiment/highest_sentiment) * rate_adjustment_ratio
    rate_guess_upper = { 2: rate_guess_2, 30: rate_guess_30, 60: rate_guess_60, 120: rate_guess_120}
    print(f"margin_split_ratio_dict: {margin_split_ratio_dict}, rate_guess_upper: {rate_guess_upper}")
    return margin_split_ratio_dict,rate_guess_upper


""" get all offers in my book """
async def list_lending_offers():
    endpoint = "auth/r/funding/offers/Symbol"
    payload = {}
    headers = {
        "Content-Type": "application/json",
        **_build_authentication_headers(endpoint, payload)
    }
    url = f"{API}/{endpoint}"
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as response:
            response.raise_for_status()
            return await response.json()

""" remove current offer in my book """
async def remove_all_lending_offer():
    endpoint = "auth/w/funding/offer/cancel/all"
    payload = {}
    headers = {
        "Content-Type": "application/json",
        **_build_authentication_headers(endpoint, payload)
    }
    url = f"{API}/{endpoint}"
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as response:
            response.raise_for_status()
            return await response.json()

"""Get available funds"""
async def available_funds(currency):
    endpoint = f"auth/r/wallets"
    payload = {}
    headers = {
        "Content-Type": "application/json",
        **_build_authentication_headers(endpoint, payload)
    }
    url = f"{API}/{endpoint}"
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as response:
            response.raise_for_status()
            res = await response.json()
            return float(res[0][4])



""" Main Function: Strategically place a lending offer on Bitfinex"""
async def place_lending_offer(currency, margin_split_ratio_dict,rate_avg_dict,offer_rate_guess_upper):
    """
    Args:
        currency (str): The currency to lend (e.g., 'UST', 'USD')
        amount (float): Amount to lend
        rate (float): Daily interest rate (in percentage)
    
    Returns:
        dict: Response from the API
    """
    funds = await available_funds(currency)
    if(funds < 150):
        print(f"Not enough funds to lend, funds: {funds}")
        return
    endpoint = "auth/w/funding/offer/submit"
    for period in margin_split_ratio_dict.keys():
        splited_fund = max(150,round(margin_split_ratio_dict[period] * funds, 2))
        segment_rate = (offer_rate_guess_upper[period] - rate_avg_dict[period]) / STEPS
        for i in range(STEPS):
            rate = round(rate_avg_dict[period] + i * segment_rate,5)
            # FRRDELTAFIX: Place an order at an implicit, static rate, relative to the FRR
            # FRRDELTAVAR: Place an order at an implicit, dynamic rate, relative to the FRR
            payload = {
                "type": "FRRDELTAVAR",
                "symbol": currency,
                "amount": splited_fund,
                "rate": rate,
                "period": period,
                "flags": 0
            }
            headers = {
                "Content-Type": "application/json",
            **await _build_authentication_headers(endpoint, payload)
        }
        url = f"{API}/{endpoint}"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as response:
                response.raise_for_status()
                return await response.json()

async def lending_bot_strategy():
    
    print("Running lending bot strategy")
    currency = os.getenv('FUND_CURRENCY')
    # get market sentiment
    sentiment = await get_market_borrow_sentiment(currency)
    # get market rate
    volume_dict,rate_upper_dict,rate_avg_dict = await get_market_funding_book(currency)
    
    # guess market rate
    margin_split_ratio_dict,offer_rate_guess_upper = guess_funding_book(volume_dict,rate_upper_dict,rate_avg_dict,sentiment)

    # get my offers and remove current offer first
    my_offers = await list_lending_offers()
    print(f"my_offers: {my_offers}")

    time.sleep(0.5)
    cancel_res = await remove_all_lending_offer()
    print(f"cancel_res: {cancel_res}")

    # place new offer
    time.sleep(0.5)
    await place_lending_offer(currency, margin_split_ratio_dict,rate_avg_dict,offer_rate_guess_upper)
    

async def run_schedule_task():
    await lending_bot_strategy()


if __name__ == '__main__':
    os_name = platform.system()
    mode = int(sys.argv[1])
    if mode == 0:
        asyncio.run(run_schedule_task())
    else:
        with ThreadPoolExecutor(max_workers=1) as executor:
            schedule.every().hour.at(":06").do(lambda: asyncio.run(run_schedule_task()))
            while True:
                schedule.run_pending()
                time.sleep(1)

