import json
from events import *
from xdg import XDG_DATA_HOME, XDG_CONFIG_HOME
import time

#location where the imported data should be stored
data_file_path = XDG_DATA_HOME + "/mistbat/cudominer.json"


def update_from_remote():
    """Look for files in XDG_DATA_HOME with the format "cudo_transactions*.json".  Look for 
    duplicate transaction ids and throw a warning."""
    import glob

    #find files which match the format we expect.
    print(f'Reading Cudo Miner files from {XDG_DATA_HOME}')
    filenames = glob.glob(XDG_DATA_HOME+"/cudo_transactions*.json")
    print(f'Found {len(filenames)} Cudo Miner files.')
    
    #read in the data from all the files found
    transactions = []
    for f in filenames:
        with open(f, newline='') as csvfile:
            transactions.extend(json.load(csvfile))
    print(f'Found {len(transactions)} CudoMiner observations.')

    #Get deposits and withdrawals
    deposits = [t for t in transactions if t['category'] == 'revenue']
    print(f"{len(deposits)} deposit transactions imported.")
    withdraws = [t for t in transactions if ((t['category'] == 'user-withdrawal') or (t['category'] == 'balance-transfer'))]
    print(f"{len(withdraws)} withdrawal transactions imported.")
    b_resources = {"deposits": deposits, "withdraws": withdraws}

    #write the file out
    print(f'Writing Cudo Miner Data to {data_file_path}...')
    with open(data_file_path, "w") as f:
        f.write(json.dumps(b_resources, indent=2))


def parse_events():
    """Take json file of Cudo Miner transactions and parse into Event instances.
    Returns:
      A list of instances of Event subclasses (e.g., Exchange, FiatExchange, Send)
      The location is "CudoMiner"+ the text in the Account Name field.
    """
    # Returns Exchanges, Sends, Receives
    # Does not do things like parse into Coins
    events = []

    # Coin ticker lookup dictionary
    ticker_lookup = {'monero':'XMR',
                    'ethereum':'ETH',
                    'ethereum-classic':'ETC',
                    'bitcoin':'BTC'
                    }
    # Load up the JSON file
    with open(data_file_path, "r") as f:
        json_data = json.load(f)

    # Format deposits as Receive Events
    for obs in json_data["deposits"]:
        receive = Receive(
            time=obs["timestamp"],
            location="CudoMiner",
            coin=ticker_lookup[obs["coin"]],
            amount=float(obs["amount"]),
        )
        events.append(receive)

    # Format withdrawals as Send Events
    for obs in json_data["withdraws"]:
        send = Send(
            time=obs["timestamp"],
            location="CudoMiner",
            coin=ticker_lookup[obs["coin"]],
            amount=abs(float(obs["amount"]))    #use absolute value since cudominer lists its withdrawal/transfer transactions as negative.
        )
        events.append(send)
    
    return events

