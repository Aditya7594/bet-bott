from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, CallbackContext, ChatMemberHandler, filters
from pymongo import MongoClient
import logging
from datetime import datetime, timedelta
from functools import wraps

# MongoDB connection setup
client = MongoClient('mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority&appName=Joybot')
db = client['telegram_bot']
users_collection = db['users']
genshin_collection = db['genshin_users']
blacklist_collection = db['blacklist']

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

    try:
        amount = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /store <amount>")
        return

    user_data = get_user_by_id(user_id)
    if not user_data:
        await update.message.reply_text("You need to start the bot first by using /start.")
        return

    if user_data['credits'] < amount:
        await update.message.reply_text(f"You don't have enough credits to store. Your balance is {user_data['credits']} credits.")
        return

    user_data['credits'] -= amount
    user_data['bank'] = user_data.get('bank', 0) + amount
    save_user(user_data)

    await update.message.reply_text(f"Successfully stored {amount} credits in your virtual bank. Your bank balance is now {user_data['bank']} credits.")

# Bank system - Withdraw credits
async def withdraw(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = str(user.id)

    try:
        amount = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /withdraw <amount>")
        return

    user_data = get_user_by_id(user_id)
    if not user_data:
        await update.message.reply_text("You need to start the bot first by using /start.")
        return

    if user_data.get('bank', 0) < amount:
        await update.message.reply_text(f"You don't have enough funds in your bank. Your bank balance is {user_data.get('bank', 0)} credits.")
        return

    user_data['credits'] += amount
    user_data['bank'] -= amount
    save_user(user_data)

    await update.message.reply_text(f"Successfully withdrew {amount} credits from your virtual bank. Your current balance is {user_data['credits']} credits.")

# Show bank balance
async def bank(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = str(user.id)

    user_data = get_user_by_id(user_id)
    if not user_data:
        await update.message.reply_text("You need to start the bot first by using /start.")
        return

    bank_balance = user_data.get('bank', 0)
    await update.message.reply_text(f"Your virtual bank balance is: {bank_balance} credits.")

# Add user to blacklist
async def blacklist(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    try:
        target_id = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /blacklist <user_id>")
        return

    blacklist_collection.update_one({"user_id": target_id}, {"$set": {"user_id": target_id}}, upsert=True)
    await update.message.reply_text(f"User ID {target_id} has been blacklisted.")

# Remove user from blacklist
async def unblacklist(update: Update, context: CallbackContext) -> None:
    try:
        target_id = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /unblacklist <user_id>")
        return

    result = blacklist_collection.delete_one({"user_id": target_id})
    if result.deleted_count > 0:
        await update.message.reply_text(f"User ID {target_id} has been removed from the blacklist.")
    else:
        await update.message.reply_text(f"User ID {target_id} was not found in the blacklist.")

# Auto-ban blacklisted users when they join
def is_blacklisted(user_id):
    return blacklist_collection.find_one({"user_id": user_id}) is not None

async def auto_ban(update: Update, context: CallbackContext):
    chat_member = update.chat_member
    user = chat_member.new_chat_member.user
    if chat_member.difference().get("status") == ("left", "member") or chat_member.new_chat_member.status != "member":
        return

    if is_blacklisted(user.id):
        try:
            await context.bot.ban_chat_member(chat_id=update.effective_chat.id, user_id=user.id)
            print(f"Banned blacklisted user {user.full_name} (ID: {user.id})")
        except Exception as e:
            print(f"Failed to ban user {user.id}: {e}")

# Register command handlers
def get_bank_handlers():
    return [
        CommandHandler("store", store),
        CommandHandler("withdraw", withdraw),
        CommandHandler("bank", bank),
        CommandHandler("blacklist", blacklist),
        CommandHandler("unblacklist", unblacklist),
        ChatMemberHandler(auto_ban, ChatMemberHandler.CHAT_MEMBER)
    ]
