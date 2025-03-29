from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, CallbackContext, filters
from pymongo import MongoClient
import logging
from datetime import datetime, timedelta
from functools import wraps

# MongoDB connection setup
client = MongoClient('mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority&appName=Joybot')
db = client['telegram_bot']
users_collection = db['users']
genshin_collection = db['genshin_users']

# Fetch user data from database
def get_user_by_id(user_id):
    return users_collection.find_one({"user_id": user_id})

def save_user(user_data):
    users_collection.update_one({"user_id": user_data["user_id"]}, {"$set": user_data}, upsert=True)

# Fetch Genshin user data from the database
def get_genshin_user_by_id(user_id):
    return genshin_collection.find_one({"user_id": user_id})

def save_genshin_user(user_data):
    genshin_collection.update_one({"user_id": user_data["user_id"]}, {"$set": user_data}, upsert=True)

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

# Bank balance command - Show user's bank balance
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

    # Show the bank balance
    await update.message.reply_text(f"Your virtual bank balance is: {bank_balance} credits.")

def get_bank_handlers():
    """Return all bank handlers."""
    return [
        CommandHandler("store", store),
        CommandHandler("withdraw", withdraw),
        CommandHandler("bank", bank)
    ]
