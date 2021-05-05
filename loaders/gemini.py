import json
from events import *
from xdg import XDG_DATA_HOME, XDG_CONFIG_HOME
import time

#location where the imported data should be stored
data_file_path = XDG_DATA_HOME + "/mistbat/gemini.json"

USE_SANDBOX = True

def update_from_remote():
    """Poll the gemini API for transfer history and trade history and save as json file."""
    from gemini import PrivateClient, PublicClient
    import yaml

    # open a public client and retrive the list of symbols and convert to upper case
    pub_client = PublicClient(sandbox=USE_SANDBOX)
    all_pairs = pub_client.symbols()    # pairs are lower case in the exchange

    # Open the private client to Gemini.
    keys = yaml.load(open(XDG_CONFIG_HOME + "/mistbat/secrets.yaml"))["gemini"]
    pvt_client = PrivateClient(keys["api_key"], keys["secret_key"])

    #read all transfers to/from Gemini
    transfers = pvt_client.get_past_transfers()
    print(f"Retrieved {len(transfers)} transfers.")
    deposits = [t for t in transfers if (t['type'] == "Deposit") and (t['status'] != "Advanced")]
    withdraws = [t for t in transfers if (t['type'] == "Withdrawal") and (t['status'] != "Advanced")]
    print(f"Accepted {len(deposits)} deposits and {len(withdraws)} withdrawals.")

    b_resources = {"deposits": deposits, "withdraws": withdraws}

    trades = {}
    print(f"Total pairs to loop through: {len(all_pairs)}")
    for index, pair in enumerate(all_pairs):
        if index % 10 == 0:
            print(f"Currently: {index}")
        try:
            # convert pair to upper case
            trades[pair.upper()] = pvt_client.get_past_trades(symbol=pair)
        except:
            print("API limit exceeded. Pausing for 5 seconds.")
            time.sleep(5)
            trades[pair.upper()] = pvt_client.get_past_trades(symbol=pair)
            

        # 500 trades max per pair
        assert len(trades[pair.upper()]) < 500

    b_resources["trades"] = trades

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

        receive = Receive(
            time=obs["timestampms"],
            location="gemini",
            coin=obs["currency"],
            amount=float(obs["amount"]),
            txid=obs["txHash"],
        )
        events.append(receive)

    for obs in json_data["withdraws"]:
        # Handle differing Bitcoin Cash symbols
        if obs["currency"] == "BCC":
            obs["currency"] = "BCH"

        send = Send(
            time=obs["timestampms"],
            location="gemini",
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

        # Only handle 3 char coins for now
        assert len(pair) == 6
        base_currency = pair[:3]
        quote_currency = pair[3:]

        # Handle differing Bitcoin Cash symbols
        if base_currency == "BCC":
            base_currency = "BCH"
        if quote_currency == "BCC":
            quote_currency = "BCH"

        for obs in all_trades[pair]:
            # Validation checks -- only processing USD
            assert obs['fee_currency'] == "USD"

            if obs["type"] == "Buy":
                fiat_exchange = FiatExchange(
                    time=obs["timestampms"],
                    location="gemini",
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
                    location="gemini",
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

        # Only handle 3 char coins for now
        assert len(pair) == 6
        base_currency = pair[:3]
        quote_currency = pair[3:]

        # Handle differing Bitcoin Cash symbols
        if base_currency == "BCC":
            base_currency = "BCH"
        if quote_currency == "BCC":
            quote_currency = "BCH"

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
                location="gemini",
                buy_coin=buy_coin,
                buy_amount=buy_amount,
                sell_coin=sell_coin,
                sell_amount=sell_amount,
                fee_with=obs["fee_currency"],
                fee_amount=float(obs["fee_amount"]),
            )
            events.append(exchange)


    return events
