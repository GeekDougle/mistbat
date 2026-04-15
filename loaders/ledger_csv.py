import json
from events import *
from xdg import XDG_DATA_HOME, XDG_CONFIG_HOME
import time
import warnings
import logging

logger = logging.getLogger(__name__)

#location where the imported data should be stored
data_file_path = XDG_DATA_HOME + "/mistbat/ledger_csv_import.json"

def update_from_remote():
    """Look for files in XDG_DATA_HOME with the format "ledgerlive-operations*.csv".  Look for 
    duplicate transaction ids and throw a warning.
    BOND, DELEGATE, UNDELEGATE transactions are ignored.
    """
    import glob
    import csv

    #find files which match the format we expect.
    logger.info(f'Reading Ledger files from {XDG_DATA_HOME}')
    filenames = glob.glob(XDG_DATA_HOME+"/ledgerlive-operations*.csv")
    logger.info(f'Found {len(filenames)} Ledger files.')
    
    #read in the data from all the files found
    transactions = []
    for f in filenames:
        with open(f, newline='') as csvfile:
            transactions.extend(csv.DictReader(csvfile))
    logger.info(f'Found {len(transactions)} Ledger observations.')

    unique_transactions = []
    for d in transactions:
        if d not in unique_transactions:
            unique_transactions.append(d)
    logger.info(f'Found {len(unique_transactions)} Unique Ledger observations.')

    #check for duplicate transaction hashes
    seen = set()
    duplicate = []  #list of indecies of duplicates
    op_hash_list = [t['Operation Hash'] for t in unique_transactions]
    for i, x in enumerate(op_hash_list):
        if x not in seen:
            seen.add(x)
        else:
            logger.warning(f'Possible Duplicate found. Operation Hash: {x}')
            #TODO: Handle multiple duplicate instances
            #find previous instance of this transaction hash
            prev_instance = unique_transactions[op_hash_list.index()]
            if (prev_instance['Operation Date'] != unique_transactions[i]['Operation Date']) or prev_instance['Account xpub'] != transactions[i]['Account xpub']:
                warnings.warn('Non Matching Duplicate Ledger Operation Hash: {}'.format(x))
            else:
                duplicate.add(i)
    #remove the duplicates from the transaction list
    if len(duplicate) >0:
        for x in duplicate:
            del unique_transactions[x]
        logger.info(f'{len(duplicate)} duplicate transactions deleted.')
        
    #Get deposits and withdrawals
    deposits = [t for t in unique_transactions if t['Operation Type'] in ('IN', 'REWARD_PAYOUT')]
    logger.info(f"{len(deposits)} deposit transactions imported.")
    withdraws = [t for t in unique_transactions if t['Operation Type'] in ('OUT')]
    logger.info(f"{len(withdraws)} withdrawal transactions imported.")
    b_resources = {"deposits": deposits, "withdraws": withdraws}

    #write the file out
    logger.debug(f'Writing Ledger Data to {data_file_path}...')
    with open(data_file_path, "w") as f:
        f.write(json.dumps(b_resources, indent=2))


def parse_events():
    """Take json file of Ledger transactions and parse into Event instances.
    Returns:
      A list of instances of Event subclasses (e.g., Exchange, FiatExchange, Send)
      The location is "Ledger"+ the text in the Account Name field.
    """
    # Returns Exchanges, Sends, Receives
    # Does not do things like parse into Coins
    events = []

    # Load up the JSON file
    with open(data_file_path, "r") as f:
        json_data = json.load(f)

    # Format deposits as Receive Events
    for obs in json_data["deposits"]:
        receive = Receive(
            time=obs["Operation Date"],
            location="Ledger" + '-' + obs['Account Name'],
            coin=obs["Currency Ticker"],
            # All my transfers are from Gemini, so the transaction fee is already captured in the fees that Gemini charges.
            amount=float(obs["Operation Amount"]),
            txid=obs["Operation Hash"],
        )
        events.append(receive)

    # Format withdrawals as Send Events
    for obs in json_data["withdraws"]:
        send = Send(
            time=obs["Operation Date"],
            location="Ledger" + '-' + obs['Account Name'],
            coin=obs["Currency Ticker"],
            amount=float(obs["Operation Amount"]),
            txid=obs["Operation Hash"],
        )
        events.append(send)

    return events