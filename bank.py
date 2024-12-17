from telegram import Update
from telegram.ext import CallbackContext
from datetime import datetime
from pymongo import MongoClient

# MongoDB connection setup
client = MongoClient('mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority&appName=Joybot')
db = client['telegram_bot']
users_collection = db['users']  # Users collection where user data is stored

# Fetch user data from database
def get_user_by_id(user_id):
    return users_collection.find_one({"user_id": user_id})

def save_user(user_data):
    users_collection.update_one({"user_id": user_data["user_id"]}, {"$set": user_data}, upsert=True)

# Exchange functionality
# Exchange functionality
async def exchange(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = str(user.id)

    # Get the amount and the type of currency to exchange
    try:
        amount = int(context.args[0])
        currency_type = context.args[1].lower()
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /exchange <amount> <currency_type (gold/silver/bronze)>")
        return

    # Fetch user data
    user_data = get_user_by_id(user_id)
    if not user_data:
        await update.message.reply_text("You need to start the bot first by using /start.")
        return

    # Determine conversion rates and check if user has enough credits
    if currency_type == "gold":
        credit_cost = 100000
    elif currency_type == "silver":
        credit_cost = 50000
    elif currency_type == "bronze":
        credit_cost = 10000
    else:
        await update.message.reply_text("Invalid currency type. Choose between 'gold', 'silver', or 'bronze'.")
        return
    
    # Corrected line: Multiply credit cost by the amount of coins requested
    total_credit_cost = amount * credit_cost
    if user_data['credits'] < total_credit_cost:
        await update.message.reply_text(f"You don't have enough credits for this exchange. You need {total_credit_cost} credits.")
        return

    # Perform the exchange
    user_data['credits'] -= total_credit_cost
    user_data['bag'][currency_type] = user_data['bag'].get(currency_type, 0) + amount
    save_user(user_data)

    await update.message.reply_text(f"Successfully exchanged {total_credit_cost} credits for {amount} {currency_type} coin(s).")

# Reverse exchange functionality (to convert coins back to credits)
async def reverse_exchange(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = str(user.id)

    # Get the amount and the type of currency to reverse exchange
    try:
        amount = int(context.args[0])
        currency_type = context.args[1].lower()
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /exchange <amount> <currency_type (gold/silver/bronze)>")
        return

    # Fetch user data
    user_data = get_user_by_id(user_id)
    if not user_data:
        await update.message.reply_text("You need to start the bot first by using /start.")
        return

    # Check if user has the coins to reverse exchange
    if currency_type not in user_data['bag'] or user_data['bag'][currency_type] < amount:
        await update.message.reply_text(f"You don't have enough {currency_type} coins to exchange.")
        return

    # Reverse the exchange
    if currency_type == "gold":
        credit_value = 100000
    elif currency_type == "silver":
        credit_value = 50000
    elif currency_type == "bronze":
        credit_value = 10000

    user_data['credits'] += amount * credit_value
    user_data['bag'][currency_type] -= amount
    save_user(user_data)

    await update.message.reply_text(f"Successfully reversed the exchange. You now have {user_data['credits']} credits and {user_data['bag'][currency_type]} {currency_type} coin(s).")

# Bank system - Store credits
async def store(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = str(user.id)

    # Get the amount to store
    try:
        amount = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /store <amount>")
        return

    # Fetch user data
    user_data = get_user_by_id(user_id)
    if not user_data:
        await update.message.reply_text("You need to start the bot first by using /start.")
        return

    if user_data['credits'] < amount:
        await update.message.reply_text(f"You don't have enough credits to store. Your balance is {user_data['credits']} credits.")
        return

    # Store credits in the virtual bank
    user_data['credits'] -= amount
    user_data['bank'] = user_data.get('bank', 0) + amount
    save_user(user_data)

    await update.message.reply_text(f"Successfully stored {amount} credits in your virtual bank. Your bank balance is now {user_data['bank']} credits.")

# Bank system - Withdraw credits
async def withdraw(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = str(user.id)

    # Get the amount to withdraw
    try:
        amount = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /withdraw <amount>")
        return

    # Fetch user data
    user_data = get_user_by_id(user_id)
    if not user_data:
        await update.message.reply_text("You need to start the bot first by using /start.")
        return

    if user_data['bank'] < amount:
        await update.message.reply_text(f"You don't have enough funds in your bank. Your bank balance is {user_data['bank']} credits.")
        return

    # Withdraw credits from the virtual bank
    user_data['credits'] += amount
    user_data['bank'] -= amount
    save_user(user_data)

    await update.message.reply_text(f"Successfully withdrew {amount} credits from your virtual bank. Your current balance is {user_data['credits']} credits.")

# Bank balance command - Show user's bank balance and deduct 37 credits
async def bank(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = str(user.id)

    # Fetch user data
    user_data = get_user_by_id(user_id)
    if not user_data:
        await update.message.reply_text("You need to start the bot first by using /start.")
        return

    # Get the user's virtual bank balance
    bank_balance = user_data.get('bank', 0)  # Default to 0 if not found

    # Check if the user has at least 37 credits in the virtual bank
    if bank_balance < 37:
        await update.message.reply_text("You don't have enough credits to check your bank balance.")
        return

    # Deduct 37 credits from the bank if the user has enough
    user_data['bank'] -= 37
    save_user(user_data)  # Save updated data

    # Show the bank balance after deduction
    await update.message.reply_text(f"Your virtual bank balance is: {bank_balance} credits.")

