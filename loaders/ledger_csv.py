import json
from events import *
from xdg import XDG_DATA_HOME, XDG_CONFIG_HOME
import time
import warnings

#location where the imported data should be stored
data_file_path = XDG_DATA_HOME + "/mistbat/ledger_csv_import.json"

def update_from_remote():
    """Look for files in XDG_DATA_HOME with the format "ledgerlive-operations*.csv".  Look for 
    duplicate transaction ids and throw a warning."""
    import glob
    import csv

    #find files which match the format we expect.
    print('Reading Ledger files from {}'.format(XDG_DATA_HOME))
    filenames = glob.glob(XDG_DATA_HOME+"/ledgerlive-operations*.csv")
    print('Found {} Ledger files.'.format(len(filenames)))
    
    #read in the data from all the files found
    transactions = []
    for f in filenames:
        with open(f, newline='') as csvfile:
            transactions.extend(csv.DictReader(csvfile))
    print('Found {} Ledger observations.'.format(len(transactions)))

    #check for duplicate transaction hashes
    seen = set()
    duplicate = []  #list of indecies of duplicates
    op_hash_list = [t['Operation Hash'] for t in transactions]
    for i, x in enumerate(op_hash_list):
        if x not in seen:
            seen.add(x)
        else:
            print('Possible Duplicate found. Operation Hash: {}'.format(x))
            #TODO: Handle multiple duplicate instances
            #find previous instance of this transaction hash
            prev_instance = transactions[op_hash_list.index()]
            if (prev_instance['Operation Date'] != transactions[i]['Operation Date']) or prev_instance['Account xpub'] != transactions[i]['Account xpub']:
                warnings.warn('Non Matching Duplicate Ledger Operation Hash: {}'.format(x))
            else:
                duplicate.add(i)
    #remove the duplicates from the transaction list
    for x in duplicate:
        del transactions[x]
    print('{} duplicate transactions deleted.  Check your source files to prevent this.'.format(len(duplicate)))
    
    #Get deposits and withdrawals
    deposits = [t for t in transactions if t['Operation Type'] == 'IN']
    print("{} deposit transactions imported.".format(len(deposits)))
    withdraws = [t for t in transactions if t['Operation Type'] == 'OUT']
    b_resources = {"deposits": deposits, "withdraws": withdraws}

    #write the file out
    print('Writing Ledger Data to {}...'.format(data_file_path))
    with open(data_file_path, "w") as f:
        f.write(json.dumps(b_resources, indent=2))


def parse_events():
    """Take json file of binance transactions and parse into Event instances.
    Returns:
      A list of instances of Event subclasses (e.g., Exchange, FiatExchange, Send)
    """
    # Returns Exchanges, Sends, Receives
    # Does not do things like parse into Coins
    events = []
    """
    # Load up the JSON file
    with open(data_file_path, "r") as f:
        json_data = json.load(f)

    for obs in json_data["deposits"]["depositList"]:
        # Handle differing Bitcoin Cash symbols
        if obs["asset"] == "BCC":
            obs["asset"] = "BCH"

        receive = Receive(
            time=obs["insertTime"],
            location="binance",
            coin=obs["asset"],
            amount=float(obs["amount"]),
            txid=obs["txId"],
        )
        events.append(receive)

    for obs in json_data["withdraws"]["withdrawList"]:
        # Handle differing Bitcoin Cash symbols
        if obs["asset"] == "BCC":
            obs["asset"] = "BCH"

        send = Send(
            time=obs["applyTime"],
            location="binance",
            coin=obs["asset"],
            amount=float(obs["amount"]),
            txid=obs["txId"],
        )
        events.append(send)

    trades = json_data["trades"]
    for pair in trades:
        if len(trades[pair]) == 0:
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

        for obs in trades[pair]:
            if obs["isBuyer"]:
                buy_coin = base_currency
                sell_coin = quote_currency
                buy_amount = float(obs["qty"])
                sell_amount = round(float(obs["price"]) * float(obs["qty"]), 8)
            else:
                buy_coin = quote_currency
                sell_coin = base_currency
                sell_amount = float(obs["qty"])
                buy_amount = round(float(obs["price"]) * float(obs["qty"]), 8)

            exchange = Exchange(
                time=obs["time"],
                location="binance",
                buy_coin=buy_coin,
                buy_amount=buy_amount,
                sell_coin=sell_coin,
                sell_amount=sell_amount,
                fee_with=obs["commissionAsset"],
                fee_amount=float(obs["commission"]),
            )
            events.append(exchange)
    """
    return events