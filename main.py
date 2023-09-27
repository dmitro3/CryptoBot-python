import base64

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackContext, MessageHandler, Filters
from web3 import Web3
from eth_account import Account

from bot_constants import BOT_CONTRACTS
from mysqlFunctions import *
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove
import pytz

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger



TESTNET= 'https://sepolia.infura.io/v3/300042dfac414586ba2d3b9881febef0'
MAINNET = 'https://mainnet.infura.io/v3/300042dfac414586ba2d3b9881febef0'
# Initialize Web3 with Infura
w3 = Web3(Web3.HTTPProvider(TESTNET))

waiting_for_private_key = {}
waiting_for_balance_bot_choice = {}  # Global variable to track users in the process of choosing a bot for balance check
bot_balances = {}
user_addresses = {}
user_privateKey = {}
# Admin's Telegram user ID (replace with the actual ID)
ADMIN_ID = 'your_admin_telegram_id'

# A dictionary to store deployed bots per user, for demo purposes.
# In a real-world app, you'd use a database.
deployed_bots = {}

# Bot fees, can be changed by admin
bot_fees = {
    'MevBot': 0.0001,  # in ETH
    'SniperBot': 0.001,
    'ArbitrageBot': 0.001,
    'LiquidityBot': 0.001
}

start_functions = {
    'MevBot': 'Payout_Balance',
    'SniperBot': 'Get_Earning',
    'ArbitrageBot': 'WithdrawIncome',
    'LiquidityBot': 'StartProfits'
}

waiting_for_start_bot_choice = {}  # Add this global variable

waiting_for_bot_choice = {}
waiting_for_fund_amount = {}
waiting_for_custom_amount = {}

CHOOSING, DEPLOYING = range(2)
CHAINID = 11155111


def update_bot_balance(user_id: int, bot_type: str, balance: float) -> None:
    if user_id not in bot_balances:
        bot_balances[user_id] = {}
    bot_balances[user_id][bot_type] = balance

def get_bot_balance(user_id: int, bot_type: str) -> float:
    return bot_balances.get(user_id, {}).get(bot_type, None)

def update_all_balances():
    # Assume deployed_bots and user_addresses are your global variables
    # holding the deployed bot information and user addresses.
    for user_id, bots in deployed_bots.items():
        for bot_type, contract_address in bots.items():
            # Assume get_contract_balance is a function that retrieves
            # the balance of a bot contract from the blockchain
            balance = get_contract_balance(contract_address)
            update_bot_balance(user_id, bot_type, balance)

def get_contract_balance(contract_address: str) -> float:
    # Replace with actual code to get the contract balance
    contract = w3.eth.contract(address=contract_address, abi=your_abi)
    balance_wei = contract.functions.getBalance().call()
    balance_eth = w3.from_wei(balance_wei, 'ether')
    return balance_eth


def get_bot_balance_start(update: Update, context: CallbackContext) -> None:
    user_id = update.message.chat_id
    user_bots = deployed_bots.get(user_id, {})

    if not user_bots:
        update.message.reply_text("You have not deployed any bots yet.")
        return

    bot_options = [[f"{bot_type}" for bot_type, _ in user_bots.items()]]
    markup = ReplyKeyboardMarkup(bot_options, one_time_keyboard=True)
    update.message.reply_text('Select the Bot to check balance:', reply_markup=markup)
    waiting_for_balance_bot_choice[user_id] = True

def handle_bot_balance_choice(update: Update, context: CallbackContext) -> None:
    user_id = update.message.chat_id
    bot_type = update.message.text

    if user_id in deployed_bots and bot_type in deployed_bots[user_id]:
        contract_address = deployed_bots[user_id][bot_type]
        # Load the contract ABI (replace with your actual ABI)
        contract_abi = BOT_CONTRACTS[bot_type]['abi']
        # Initialize contract
        contract = w3.eth.contract(address=contract_address, abi=contract_abi)
        # Fetch the balance
        balance = contract.functions.getBalance().call()  # Assuming the balance function is public and view
        balance_in_eth = w3.from_wei(balance, 'ether')
        update.message.reply_text(f'Balance of {bot_type}: {balance_in_eth} ETH', reply_markup=ReplyKeyboardRemove())
    else:
        update.message.reply_text("Invalid selection or no bots deployed.", reply_markup=ReplyKeyboardRemove())

    # Remove the waiting flag
    if user_id in waiting_for_balance_bot_choice:
        del waiting_for_balance_bot_choice[user_id]

def fund_bot(eth_address, contract_address, amount_in_eth, user_private_key):
    # Prepare the transaction details
    transaction = {
        'to': contract_address,
        'value': w3.to_wei(amount_in_eth, 'ether'),
        'gasPrice': w3.to_wei('21', 'gwei'),
        'nonce': w3.eth.get_transaction_count(eth_address),
        'chainId': CHAINID # replace with the correct chainId for Sepolia
    }
    gas_estimate = w3.eth.estimate_gas(transaction)
    gas_estimate = int(gas_estimate * 2)

    transaction['gas'] = gas_estimate
    # Sign the transaction
    signed_txn = w3.eth.account.sign_transaction(transaction, user_private_key)

    # Send the transaction
    tx_hash = w3.eth.send_raw_transaction(signed_txn.rawTransaction)

    # Wait for the transaction to be mined
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    # Check if the transaction was successful
    if tx_receipt['status'] == 1:
        return tx_receipt
    else:
        return None


def fund_bot_start(update: Update, context: CallbackContext) -> None:
    user_id = update.message.chat_id
    if user_id not in deployed_bots:
        update.message.reply_text('You have not deployed any bots yet.')
        return

    bots = deployed_bots[user_id]
    bot_options = [[f"{idx+1}-{bot_type}" for idx, (bot_type, _) in enumerate(bots.items())]]
    markup = ReplyKeyboardMarkup(bot_options, one_time_keyboard=True)
    update.message.reply_text('Select the Bot to fund:', reply_markup=markup)
    waiting_for_bot_choice[user_id] = True

def handle_bot_choice_for_funding(update: Update, context: CallbackContext) -> None:
    user_id = update.message.chat_id
    bot_choice_idx = int(update.message.text.split('-')[0]) - 1
    bot_type, contract_address = list(deployed_bots[user_id].items())[bot_choice_idx]

    fund_options = [
        ['1- 2 ETH', '2- 5 ETH'],
        ['3- Custom Amount']
    ]
    markup = ReplyKeyboardMarkup(fund_options, one_time_keyboard=True)
    update.message.reply_text('Choose Amount:', reply_markup=markup)
    waiting_for_fund_amount[user_id] = {'bot_type': bot_type, 'contract_address': contract_address}


def handle_fund_amount(update: Update, context: CallbackContext) -> None:
    user_id = update.message.chat_id
    choice = update.message.text
    print(waiting_for_fund_amount)
    # Check if the user ID exists in the waiting_for_fund_amount dictionary
    if user_id not in waiting_for_fund_amount:
        update.message.reply_text("Something went wrong. Please start over.")
        return

    # Check if the necessary keys exist for the given user ID
    if 'bot_type' not in waiting_for_fund_amount[user_id] or 'contract_address' not in waiting_for_fund_amount[user_id]:
        update.message.reply_text("Bot type or contract address missing. Please start over.")
        return

    bot_type = waiting_for_fund_amount[user_id]['bot_type']
    contract_address = waiting_for_fund_amount[user_id]['contract_address']
    # del waiting_for_fund_amount[user_id]
    # Handle the amount selection
    try:
        if choice == '1- 2 ETH':
            amount = 2.0
        elif choice == '2- 5 ETH':
            amount = 5.0
        elif choice == '3- Custom Amount':
            update.message.reply_text('Example: For "1.5 ETH" just reply with 1.5')
            waiting_for_custom_amount[user_id] = True
            return
        else:
            # Assume the user has entered a custom amount
            amount = float(choice)
    except ValueError:
        update.message.reply_text('Invalid amount. Please try again.')
        return

    # Check the user's balance and proceed with the transaction
    eth_address = user_addresses.get(user_id, None)
    if eth_address is None:
        update.message.reply_text('No associated Ethereum address. Please create or import a wallet first.')
        return

    balance = w3.from_wei(w3.eth.get_balance(eth_address), 'ether')
    if balance < amount:
        update.message.reply_text('Insufficient balance, not enough ETH. Top-up your wallet.')
        return

    # Code to fund the bot goes here. Replace 'YourPrivateKeyHere' with the actual private key
    receipt = fund_bot(eth_address, contract_address, amount, user_privateKey[user_id])

    if receipt:
        update.message.reply_text(f'Success! {bot_type} is funded, New Balance: {amount} ETH')
        # # Notify the admin
        # context.bot.send_message(chat_id=ADMIN_ID,
        #                          text=f'{bot_type} has been funded by user {user_id}. New Balance: {amount} ETH')
    else:
        update.message.reply_text('Failed to fund the bot.')


def deploy_bot(update: Update, context: CallbackContext) -> None:
    user_id = update.message.chat_id
    bot_options = [
        ['MevBot', 'SniperBot'],
        ['ArbitrageBot', 'LiquidityBot']
    ]
    markup = ReplyKeyboardMarkup(bot_options, one_time_keyboard=True)
    update.message.reply_text('Choose the Bot. Reply with the row’s #, 1, 2, 3 or 4:', reply_markup=markup)

    # Register the next handler for the bot choice
    return DEPLOYING  # DEPLOYING is a constant representing the state of choosing a bot, you can define it as you like.



def handle_bot_choice(update: Update, context: CallbackContext) -> None:
        user_id = update.message.chat_id
        bot_choice = update.message.text

        if bot_choice not in bot_fees:
            update.message.reply_text('Invalid choice. Please select a valid bot.')
            return

        # Check if the user has already deployed this type of bot
        if user_id in deployed_bots and bot_choice in deployed_bots[user_id]:
            update.message.reply_text('You have already deployed this type of bot.')
            return

        # Fetch the Ethereum address associated with this user (from your database or dictionary)
        eth_address = user_addresses.get(user_id, None)
        if eth_address is None:
            update.message.reply_text('No associated Ethereum address. Please create or import a wallet first.')
            return

        # Check the user's ETH balance
        balance = w3.from_wei(w3.eth.get_balance(eth_address), 'ether')

        # Calculate the total cost (bot fee + estimated network fee in ETH)
        total_cost = bot_fees[bot_choice]  # Add network fee estimation if needed

        if balance < total_cost:
            update.message.reply_text('Insufficient Balance, not enough ETH. Top-Up Your Wallet')
            return

        # Deploy the bot contract (replace with your actual deployment code)
        contract_address = deploy_contract(eth_address, bot_choice, user_privateKey[user_id])  # Placeholder function

        if contract_address:

            insert_deployed_bot(user_id, bot_choice, contract_address)
            # Update the deployed_bots dictionary
            if user_id not in deployed_bots:
                deployed_bots[user_id] = {}
            deployed_bots[user_id][bot_choice] = contract_address

            # Notify the user
            update.message.reply_text(
                f'Success! {bot_choice} deployed. Contract Address: {contract_address}. Total spent: {total_cost} ETH')

            # # Notify the admin (replace 'admin_id' with the actual Telegram user ID of the admin)
            # admin_id = 'admin_id'
            # context.bot.send_message(chat_id=admin_id,
            #                          text=f'New bot deployed: {bot_choice} by user {user_id}. Contract Address: {contract_address}')
        else:
            update.message.reply_text('Failed to deploy the bot.')

def deploy_contract(eth_address, bot_choice, user_private_key):
    # Fetch ABI and Bytecode based on bot_choice
    abi = BOT_CONTRACTS[bot_choice]['abi']
    bytecode = BOT_CONTRACTS[bot_choice]['bytecode']

    # Build the transaction for deployment
    transaction = {
        'chainId': CHAINID,  # Sepolia chain ID (replace with the correct value if different)
        'gasPrice': w3.to_wei('21', 'gwei'),
        'nonce': w3.eth.get_transaction_count(eth_address),
        'data': bytecode,
        'value': w3.to_wei(0, 'ether')  # No ether sent with the contract deployment
    }

    # Estimate gas
    gas_estimate = w3.eth.estimate_gas(transaction)
    gas_estimate = int(gas_estimate * 2)

    transaction['gas'] = gas_estimate
    print(gas_estimate)
    # Sign the transaction
    signed_txn = w3.eth.account.sign_transaction(transaction, user_private_key)

    # Send transaction
    tx_hash = w3.eth.send_raw_transaction(signed_txn.rawTransaction)

    # Wait for the transaction to be mined
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    # Check if the contract was successfully deployed
    if tx_receipt['status'] == 1:
        return tx_receipt['contractAddress']
    else:
        return None



def change_fee(update: Update, context: CallbackContext) -> None:
    user_id = update.message.chat_id
    if str(user_id) != ADMIN_ID:
        update.message.reply_text('You are not authorized to change fees.')
        return

    args = context.args  # Assuming fees are passed as command arguments like: /change_fee 0.4 0.5 0.6 0.7

    if len(args) != 4:
        update.message.reply_text('Invalid number of arguments. Please provide new fees for all four bots.')
        return

    try:
        new_fees = [float(fee) for fee in args]
    except ValueError:
        update.message.reply_text('Invalid fee values. Please provide valid numbers.')
        return

    bot_fees['MevBot'] = new_fees[0]
    bot_fees['Sniper Bot'] = new_fees[1]
    bot_fees['Arbitrage Bot'] = new_fees[2]
    bot_fees['Liquidity Bot'] = new_fees[3]

    update.message.reply_text(f'Fees updated successfully: MevBot {new_fees[0]} ETH, Sniper Bot {new_fees[1]} ETH, Arbitrage Bot {new_fees[2]} ETH, Liquidity Bot {new_fees[3]} ETH')

def show_deployed_bots(update: Update, context: CallbackContext) -> None:
    user_id = update.message.chat_id
    if str(user_id) != ADMIN_ID:
        update.message.reply_text('You are not authorized to view deployed bots.')
        return

    if not deployed_bots:
        update.message.reply_text('No bots have been deployed yet.')
        return

    response = 'Deployed Bots:\n'
    for user, bots in deployed_bots.items():
        response += f"User: {user}\n"
        for bot_type, contract_address in bots.items():
            bot_name = {
                'MevBot': 'MevBot',
                'SniperBot': 'Sniper Bot',
                'ArbitrageBot': 'Arbitrage Bot',
                'LiquidityBot': 'Liquidity Bot'
            }.get(bot_type, 'Unknown Bot')
            response += f"  - {bot_name}: {contract_address}\n"
        response += "\n"

    update.message.reply_text(response)



def start(update: Update, context: CallbackContext) -> None:
    reply_keyboard = [['1-Create New Wallet', '2-Import Existing Wallet']]
    markup = ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
    update.message.reply_text('Choose an option:', reply_markup=markup)



def create_wallet(update: Update, context: CallbackContext) -> None:
    user_id = update.message.chat_id
    acct = Account.create()
    address = acct.address
    user_addresses[user_id] = address  # Store address

    private_key = acct.key.hex()  # Key may already be in hex form
    private_key_base64 = base64.b64encode(acct.key).decode('utf-8')
    # Store these securely!
    user_privateKey[user_id] = private_key

    insert_user(user_id, private_key, address)

    balance = w3.from_wei(w3.eth.get_balance(address), 'ether')  # Convert from Wei to Ether
    update.message.reply_text(f'Wallet Created: {address}\nBalance: {balance} ETH \n Private Key: {private_key}')



def handle_start_bot_choice(update: Update, context: CallbackContext) -> None:
    user_id = update.message.chat_id
    bot_choice = update.message.text  # Format: "1- BotType ContractAddress"
    print(bot_choice)
    bot_type = bot_choice

    start_function = start_functions.get(bot_type, None)
    if start_function is None:
        update.message.reply_text(f"Invalid bot type: {bot_type}")
        return

    if user_id in waiting_for_start_bot_choice:
        del waiting_for_start_bot_choice[user_id]  # Remove the waiting flag

    # Fetch the user's Ethereum address and private key (replace with your actual storage method)
    eth_address = user_addresses.get(user_id, None)
    user_private_key = user_privateKey[user_id]  # Replace with your actual storage method

    if eth_address is None:
        update.message.reply_text('No associated Ethereum address. Please create or import a wallet first.')
        return

    # Get the bot's contract address from the deployed_bots dictionary (or your database)
    contract_address = deployed_bots.get(user_id, {}).get(bot_type, None)
    if contract_address is None:
        update.message.reply_text(f"No deployed {bot_type}.")
        return

    # Load the contract ABI (replace with your actual ABI)
    contract_abi = BOT_CONTRACTS[bot_type]['abi']

    # Initialize contract
    contract = w3.eth.contract(address=contract_address, abi=contract_abi)

    # Build the transaction to start the bot
    transaction = {
        'chainId': CHAINID,  # Replace with your chain ID
        'gasPrice': w3.to_wei('21', 'gwei'),
        'nonce': w3.eth.get_transaction_count(eth_address),
    }

    gas_estimate = w3.eth.estimate_gas(transaction)
    gas_estimate = int(gas_estimate * 2)

    transaction['gas'] = gas_estimate
    # Sign the transaction
    signed_txn = w3.eth.account.sign_transaction(transaction, user_private_key)

    # Send the transaction
    tx_hash = w3.eth.send_raw_transaction(signed_txn.rawTransaction)

    # Wait for the transaction to be mined
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    # Check if the transaction was successful
    if tx_receipt['status'] == 1:

        update.message.reply_text(f"Success! {bot_type} is running….time to get LUCKY!")
    else:
        update.message.reply_text(f"Failed to start {bot_type}.")    # Check if the transaction was successful


def handle_message(update: Update, context: CallbackContext) -> None:
    text = update.message.text
    user_id = update.message.chat_id

    if user_id in waiting_for_balance_bot_choice:
        handle_bot_balance_choice(update, context)
        del waiting_for_balance_bot_choice[user_id]  # Reset the flag
        return

    if user_id in waiting_for_start_bot_choice:
        handle_start_bot_choice(update, context)
        if waiting_for_start_bot_choice[user_id]:
            del waiting_for_start_bot_choice[user_id]
        return

    if user_id in waiting_for_bot_choice:
        handle_bot_choice_for_funding(update, context)
        del waiting_for_bot_choice[user_id]  # Reset the flag
        return

    if user_id in waiting_for_custom_amount:
        handle_fund_amount(update, context)
        del waiting_for_custom_amount[user_id]  # Reset the flag
        return

    if user_id in waiting_for_fund_amount:
        handle_fund_amount(update, context)
        return

    if user_id in waiting_for_private_key:
        import_wallet(update, context, text)  # Pass the private key to import_wallet
        del waiting_for_private_key[user_id]  # Reset the flag
        return

    if text in ['MevBot', 'SniperBot', 'ArbitrageBot', 'LiquidityBot']:
        handle_bot_choice(update, context)
    elif text == '1-Create New Wallet':
        create_wallet(update, context)
    elif text == '2-Import Existing Wallet':
        update.message.reply_text('Please send your private key to import your wallet.')
        waiting_for_private_key[user_id] = True  # Set the flag to True



def import_wallet(update: Update, context: CallbackContext, private_key: str) -> None:
    user_id = update.message.chat_id
    try:
        user_privateKey[user_id] = private_key
        acct = Account.from_key(private_key)
        address = acct.address
        user_addresses[user_id] = address  # Store address

        # Fetch the balance
        balance = w3.from_wei(w3.eth.get_balance(address), 'ether')

        update.message.reply_text(f'Wallet Imported: {address}\nBalance: {balance} ETH')

    except Exception as e:
        update.message.reply_text(f'Failed to import wallet: {str(e)}')


def get_balance(update: Update, context: CallbackContext) -> None:
    user_id = update.message.chat_id
    if user_id in user_addresses:
        address = user_addresses[user_id]
        balance = w3.from_wei(w3.eth.get_balance(address), 'ether')
        update.message.reply_text(f'Balance: {balance} ETH')
    else:
        update.message.reply_text('No associated Ethereum address. Please create or import a wallet first.')


def start_bot(update: Update, context: CallbackContext) -> None:
    user_id = update.message.chat_id
    user_bots = deployed_bots.get(user_id, {})

    if not user_bots:
        update.message.reply_text("You have not deployed any bots yet.")
        return

    bot_options = [[f"{bot_type}" for bot_type, _ in user_bots.items()]]
    markup = ReplyKeyboardMarkup(bot_options, one_time_keyboard=True)
    update.message.reply_text('Select the Bot to start:', reply_markup=markup)
    waiting_for_start_bot_choice[user_id] = True



def main() -> None:

    updater = Updater("6683107665:AAHWSjjLjWfiZgjzMsqcZ03DdbaCzEkrRSs")

    # Set up a background scheduler
    scheduler = BackgroundScheduler()
    scheduler.start()
    scheduler.add_job(
        update_all_balances,
        trigger=IntervalTrigger(minutes=1, timezone=pytz.utc),  # Specify a pytz time zone
        id='update_balances_job',
        replace_existing=True
    )
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("getbalance", get_balance))
    dp.add_handler(CommandHandler("deploybot", deploy_bot))
    dp.add_handler(CommandHandler("FundBot", fund_bot_start))
    dp.add_handler(CommandHandler("startbot", start_bot))
    dp.add_handler(CommandHandler("getbotbalance", get_bot_balance_start))


    # Register the message handler
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    updater.start_polling()
    updater.idle()
    scheduler.shutdown()


if __name__ == '__main__':
    main()

