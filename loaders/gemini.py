import json
from events import *
from xdg import XDG_DATA_HOME, XDG_CONFIG_HOME
import time
from datetime import datetime
import logging
import sys
import os

# Add parent directories to path to import logging_config
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from logging_config import progressBar

logger = logging.getLogger(__name__)

#location where the imported data should be stored
data_file_path = XDG_DATA_HOME + "/mistbat/gemini.json"

USE_SANDBOX = True

DEPRECATED_PAIRS_TO_QUERY = ('audiousd',)        #TODO: Change this to a config file.
LIMIT_TRANSFERS = 10000             #Was hard coded to 500, changing to an option which is set here.  Need >500, but don't know what the upper limit is.

def _parse_pair(pair_str):
    '''Parses the pair string into the quote currency (first symbol) and the base currency (2nd symbol)'''
    # Only handle 3 char coins for now unless one is USD
    if "USD" in pair_str:
        # is the USD the base or quote currency?
        index = pair_str.find("USD")
        if  index == 0:
            base_currency = pair_str[:3]
            quote_currency = pair_str[3:]
        else:
            base_currency = pair_str[:index]
            quote_currency = pair_str[index:]
    else:
        assert len(pair_str) == 6
    
    # Handle differing Bitcoin Cash symbols
    if base_currency == "BCC":
        base_currency = "BCH"
    if quote_currency == "BCC":
        quote_currency = "BCH"
    return(base_currency, quote_currency)


def update_from_remote(pairs:list = None):
    """Poll the gemini API for transfer history and trade history and save as json file."""
    from gemini import PrivateClient, PublicClient
    import yaml

    # open a public client and retrive the list of symbols and convert to upper case
    pub_client = PublicClient(sandbox=USE_SANDBOX)
    all_pairs = pub_client.symbols()    # pairs are lower case in the exchange
    for p in DEPRECATED_PAIRS_TO_QUERY:
        all_pairs.append(p)

    # if pairs is passed in, verify they are all valid
    if pairs is not None:
        reduced_pairs = []
        for p in pairs:
            if p in all_pairs:
                reduced_pairs.append(p)
            else:
                logger.warning(f"Pair not recognized by Gemini passed in: {p}")
        all_pairs = reduced_pairs

    # Open the private client to Gemini.
    keys = yaml.load(open(XDG_CONFIG_HOME + "/mistbat/secrets.yaml"))["gemini"]
    pvt_client = PrivateClient(keys["api_key"], keys["secret_key"])

    #read all transfers to/from Gemini
    transfers = pvt_client.get_past_transfers(limit_transfers=LIMIT_TRANSFERS)
    logger.info(f"Retrieved {len(transfers)} transfers.")

    #filtering out fiat money transfers into Gemini, since that is not a taxable event.
    deposits = [t for t in transfers if (t['type'] == "Deposit") and (t['currency'] != "USD")]
    for t in deposits:
        t['account']='gemini'
    withdraws = [t for t in transfers if (t['type'] == "Withdrawal") and (t['status'] != "Advanced")]
    for t in withdraws:
        t['account']='gemini'
    logger.info(f"Accepted {len(deposits)} deposits and {len(withdraws)} withdrawals.")
    rejected_transfers = [t for t in transfers if (t not in deposits) and (t not in withdraws)]
    logger.info(f"The following {len(rejected_transfers)} transactions weren't accepted:")
    for rt in rejected_transfers:
        logger.warning(rt)

    b_resources = {"deposits": deposits, "withdraws": withdraws}

    # #read all staking events
    staking_events = pvt_client.get_staking_history(limit_transfers=LIMIT_TRANSFERS)
    for provider in staking_events:
        logger.info(f"Retrieved {len(provider['transactions'])} staking reward events from {provider['providerId']}.")
        for event in provider['transactions']:
            txn = {"timestampms":event['dateTime'], 
                   "currency":event['amountCurrency'], 
                   "amount":event['amount'],
                   "txType": event['transactionType'],
                   "account":"gemini-stake"
                   }
            if event['transactionType'] in ['Interest']:
                b_resources['deposits'].append(txn)
            elif event['transactionType'] in ['Deposit']:
                b_resources['deposits'].append(txn)
                #have to add a transaction to remove the balance from my gemini non-staking account
                txn['amount'] = -event['amount']
                txn["account"] = "gemini"
                b_resources['withdraws'].append(txn)
            elif event['transactionType'] in ['Redeem']:
                b_resources['withdraws'].append(txn)
                #have to add a transaction to add the balance to my gemini non-staking account
                txn['amount'] = -event['amount']
                txn["account"] = "gemini-stake"
                b_resources['deposits'].append(txn)
            else:
                logger.warning(event)

    trades = {}
    logger.info(f"Total pairs to loop through: {len(all_pairs)}")
    for pair in progressBar(all_pairs, prefix = 'Progress:', suffix = 'Complete', length = 50):
        try:
            # convert pair to upper case
            trades[pair.upper()] = pvt_client.get_past_trades(symbol=pair, limit_trades=LIMIT_TRANSFERS)
        except:
            logger.warning("API limit exceeded. Pausing for 5 seconds.")
            time.sleep(5)
            trades[pair.upper()] = pvt_client.get_past_trades(symbol=pair, limit_trades=LIMIT_TRANSFERS)
        #if gemini returns an error when pulling trades, drop the pair, but print a message
        if 'result' in trades[pair.upper()]:
            logger.error(f"Error received from Gemini: {trades[pair.upper()]}")
            del trades[pair.upper()]
        else:
           for t in trades[pair.upper()]:
                t['account']='gemini'     
            

    b_resources["trades"] = trades

    logger.debug(f'Writing Gemini Data to {data_file_path}...')
    with open(data_file_path, "w") as f:
        f.write(json.dumps(b_resources, indent=2))


def parse_events():
    """Take json file of gemini transactions and parse into Event instances.
    Returns:
      A list of instances of Event subclasses (e.g., Exchange, FiatExchange, Send)
    """
    # Returns Exchanges, Sends, Receives
    # Does not do things like parse into Coins
    events = []

    # Load up the JSON file
    with open(data_file_path, "r") as f:
        json_data = json.load(f)

    for obs in json_data["deposits"]:
        # Handle differing Bitcoin Cash symbols
        if obs["currency"] == "BCC":
            obs["currency"] = "BCH"
        try:
            temp_var= obs["txHash"]
        except KeyError:
            #staking transactions don't have a hash...
            receive = Receive(
                time=obs["timestampms"],
                location=obs["account"],
                coin=obs["currency"],
                amount=float(obs["amount"]),
            )
        else:
            receive = Receive(
                time=obs["timestampms"],
                location=obs["account"],
                coin=obs["currency"],
                amount=float(obs["amount"]),
                txid=obs["txHash"],
            )
        events.append(receive)

    for obs in json_data["withdraws"]:
        # Handle differing Bitcoin Cash symbols
        if obs["currency"] == "BCC":
            obs["currency"] = "BCH"
        try:
            temp_var= obs["txHash"]
        except KeyError:
            # some Gemini withdrawals don't have a txHash.  Seems like maybe internal transfers?
            send = Send(
                time=obs["timestampms"],
                location=obs["account"],
                coin=obs["currency"],
                amount=float(obs["amount"]),
            )
        else:
            send = Send(
                time=obs["timestampms"],
                location=obs["account"],
                coin=obs["currency"],
                amount=float(obs["amount"]),
                txid=obs["txHash"],
            )
        events.append(send)

    all_trades = json_data["trades"]
    fiat_pairs = [pair for pair in all_trades if "USD" in pair]
    exchange_pairs = [pair for pair in all_trades if not("USD" in pair)]
    # process fiat trades
    for pair in fiat_pairs:
        if len(all_trades[pair]) == 0:
            continue

        base_currency, quote_currency = _parse_pair(pair)

        for obs in all_trades[pair]:
            # Validation checks -- only processing USD
            assert obs['fee_currency'] == "USD"

            if obs["type"] == "Buy":
                fiat_exchange = FiatExchange(
                    time=obs["timestampms"],
                    location=obs["account"],
                    buy_coin=base_currency,
                    buy_amount=float(obs["amount"]),
                    sell_coin="USD",
                    sell_amount=float(obs["price"]) * float(obs["amount"]),
                    fee_with="USD",
                    fee_amount=float(obs['fee_amount']),
                    location_id=str(obs["tid"]),    # Event module requirees location ID be a string 
                )
            else:
                fiat_exchange = FiatExchange(
                    time=obs["timestampms"],
                    location=obs["account"],
                    sell_coin=base_currency,
                    sell_amount=float(obs["amount"]),
                    buy_coin="USD",
                    buy_amount=float(obs["price"]) * float(obs["amount"]),
                    fee_with="USD",
                    fee_amount=float(obs['fee_amount']),
                    location_id=str(obs["tid"]),    # Event module requirees location ID be a string 
                )

            events.append(fiat_exchange)

    # process crypto<-->crypto trades
    # TODO- TEST THIS.  I don't have sample data to test this yet...
    for pair in exchange_pairs:
        if len(all_trades[pair]) == 0:
            continue

        base_currency, quote_currency = _parse_pair(pair)

        for obs in all_trades[pair]:
            if obs["type"] == "Buy":
                buy_coin = base_currency
                sell_coin = quote_currency
                buy_amount = float(obs["amount"])
                sell_amount = round(float(obs["amount"]) / float(obs["price"]), 8)
            else:
                buy_coin = quote_currency
                sell_coin = base_currency
                sell_amount = float(obs["amount"])
                buy_amount = round(float(obs["amount"]) / float(obs["price"]), 8)

            exchange = Exchange(
                time=obs["timestampms"],
                location=obs["account"],
                buy_coin=buy_coin,
                buy_amount=buy_amount,
                sell_coin=sell_coin,
                sell_amount=sell_amount,
                fee_with=obs["fee_currency"],
                fee_amount=float(obs["fee_amount"]),
            )
            events.append(exchange)


    return events
